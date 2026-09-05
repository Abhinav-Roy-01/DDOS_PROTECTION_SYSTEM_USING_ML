from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from ml_engine import predict as ml_predict
from rate_limiter import (
    check_rate_limit, record_request, is_banned,
    get_stats, get_matrix, manual_ban, record_click, get_click_feed
)
import attack_simulator
from auth import require_admin_key, get_admin_key
import time
import os
import os as _os
import sys as _sys

# captcha_routes.py lives in ../CAPTCHA/ after the CAPS reorganization
# (it used to sit next to server.py, so a plain "from captcha_routes import"
# used to work). Same class of bug as the ML model path and the
# templates/static path -- add CAPTCHA/ to sys.path before importing.
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "CAPTCHA"))

try:
    from captcha_routes import captcha_bp, get_redis
except Exception as e:
    # Was a bare "except: pass" before -- that's exactly why this bug
    # went unnoticed. Now it prints the real reason if it ever breaks again.
    print("Warning: Could not import captcha_routes:", e)

# templates/ and static/ live in ../DASHBOARD/ after the CAPS reorganization
# (they used to sit next to server.py) -- pointed here instead of moving
# them back, so DASHBOARD/ stays the single home for all frontend assets.
_api_dir = _os.path.dirname(_os.path.abspath(__file__))
_dashboard_dir = _os.path.join(_api_dir, "..", "DASHBOARD")

app = Flask(
    __name__,
    static_folder=_os.path.join(_dashboard_dir, "static"),
    template_folder=_os.path.join(_dashboard_dir, "templates"),
)
CORS(app)

try:
    app.register_blueprint(captcha_bp)
except Exception as e:
    print("Warning: Could not register captcha blueprint", e)

@app.before_request
def limiter_and_ban_check():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    path = request.path
    
    # Exclude static/captcha paths (avoid loops) and every dashboard-facing
    # control/read endpoint under /api/, plus /stats and /health.
    # These are operator-facing, not visitor-facing content routes -- if the
    # dashboard's OWN ip ever gets captcha-flagged (e.g. from testing /predict
    # with bot-like values), the dashboard itself must stay reachable so you
    # can see what happened and solve the challenge, rather than going dark.
    # /health specifically must never be gated: a Docker/K8s liveness probe
    # hitting it would see failures and could restart the container in a loop.
    if (path.startswith("/static") or path.startswith("/captcha")
            or path.startswith("/matrix") or path.startswith("/api/")
            or path == "/stats" or path == "/health"):
        return

    if is_banned(ip):
        record_request(ip, path, request.method, blocked=True)
        return jsonify({"error": "Banned"}), 403

    if not check_rate_limit(ip):
        record_request(ip, path, request.method, blocked=True)
        return jsonify({"error": "Too Many Requests - Auto Banned"}), 429

    # Check if IP needs captcha verification
    try:
        r = get_redis()
        if r.exists(f"captcha:required:{ip}") and not r.exists(f"captcha:verified:{ip}"):
            if request.accept_mimetypes.accept_html:
                return redirect(url_for("captcha.new_game"))
            return jsonify({"error": "Captcha required", "redirect": "/captcha/new_game"}), 403
    except:
        pass

@app.route('/')
def dashboard():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    record_request(ip, "/", "GET", blocked=False)
    # Inject this server's own admin key into the page so the dashboard's
    # own fetch() calls can authenticate automatically -- see auth.py.
    return render_template('dashboard.html', admin_key=get_admin_key())

@app.route('/predict', methods=['POST'])
def run_predict():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    data = request.json or {}
    
    try:
        result = ml_predict(data)
        score = result["anomaly_score"]
        pred = result["prediction"]

        # Store the raw behavioral snapshot for the live telemetry panel,
        # regardless of verdict -- this is what makes mouse/click/keystroke
        # activity visible in the dashboard in real time.
        record_click({**data, "ip": ip, "prediction": pred, "anomaly_score": score})

        # Determine Routing based on score
        # Rules: < -0.15 = Block, -0.15 to 0.10 = CAPTCHA, > 0.10 = Allow (Human)
        if score < -0.15:
            manual_ban(ip)
            record_request(ip, "/predict", "POST", blocked=True, ml_verdict=pred, ml_score=score)
            return jsonify({"status": "blocked", "message": "Bot behavior detected.", "prediction": pred, "anomaly_score": score}), 403
            
        elif -0.15 <= score <= 0.10:
            try:
                r = get_redis()
                r.set(f"captcha:required:{ip}", 1, ex=3600)
            except:
                pass
            record_request(ip, "/predict", "POST", blocked=False, ml_verdict="suspicious", ml_score=score)
            return jsonify({"status": "captcha_required", "redirect": "/captcha/new_game", "prediction": pred, "anomaly_score": score}), 403
            
        else:
            record_request(ip, "/predict", "POST", blocked=False, ml_verdict="human", ml_score=score)
            return jsonify({"status": "allowed", "prediction": "human", "anomaly_score": score}), 200
            
    except Exception as e:
        print("ML Prediction Error:", e)
        return jsonify({"error": "Prediction failed", "details": str(e)}), 500

@app.route('/matrix')
def matrix_data():
    return jsonify(get_matrix())

@app.route('/stats')
def stats_data():
    return jsonify(get_stats())

@app.route('/api/ban', methods=['POST'])
@require_admin_key
def api_manual_ban():
    data = request.json or {}
    ip = data.get("ip")
    if ip:
        manual_ban(ip)
        return jsonify({"status": "banned", "ip": ip})
    return jsonify({"error": "Missing IP"}), 400

@app.route('/api/attack/start', methods=['POST'])
@require_admin_key
def api_attack_start():
    data = request.json or {}
    attack_type = data.get("type", "flood")
    return jsonify(attack_simulator.start_attack(attack_type))

@app.route('/api/attack/stop', methods=['POST'])
@require_admin_key
def api_attack_stop():
    return jsonify(attack_simulator.stop_attack())

@app.route('/api/attack/status')
@require_admin_key
def api_attack_status():
    return jsonify(attack_simulator.get_status())

@app.route('/api/telemetry')
@require_admin_key
def api_telemetry():
    return jsonify(get_click_feed())

@app.route('/health')
def health_check():
    return jsonify({"status": "OK"})

if __name__ == '__main__':
    print("=====================================================")
    print("  Unified DDoS System running on http://127.0.0.1:8080")
    print("=====================================================")
    app.run(host='0.0.0.0', port=8080, debug=True)