from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
from ml_engine import predict as ml_predict
from rate_limiter import (
    check_rate_limit, record_request, is_banned,
    get_stats, get_matrix, manual_ban
)
import time
import os

try:
    from captcha_routes import captcha_bp, get_redis
except:
    pass

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

try:
    app.register_blueprint(captcha_bp)
except Exception as e:
    print("Warning: Could not register captcha blueprint", e)

@app.before_request
def limiter_and_ban_check():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    path = request.path
    
    # Exclude static/captcha paths to prevent loops
    if path.startswith("/static") or path.startswith("/captcha") or path.startswith("/matrix"):
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
    return render_template('dashboard.html')

@app.route('/predict', methods=['POST'])
def run_predict():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    data = request.json or {}
    
    try:
        result = ml_predict(data)
        score = result["anomaly_score"]
        pred = result["prediction"]
        
        # Determine Routing based on score
        # Rules: < -0.15 = Block, -0.15 to 0.10 = CAPTCHA, > 0.10 = Allow (Human)
        if score < -0.15:
            manual_ban(ip)
            record_request(ip, "/predict", "POST", blocked=True, ml_verdict=pred, ml_score=score)
            return jsonify({"status": "blocked", "message": "Bot behavior detected.", "prediction": pred, "anomaly_score": score}), 403
            
        elif -0.15 <= score <= 0.10:
            try:
                r = get_redis()
                r.setex(f"captcha:required:{ip}", 3600, 1)
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
def api_manual_ban():
    data = request.json or {}
    ip = data.get("ip")
    if ip:
        manual_ban(ip)
        return jsonify({"status": "banned", "ip": ip})
    return jsonify({"error": "Missing IP"}), 400

@app.route('/api/attack', methods=['POST'])
def simulate_attack():
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1")
    data = request.json or {}
    # Simulate a bunch of bad requests instantly from a dummy IP
    dummy_ip = "192.168.1.99"
    if data.get("type") == "flood":
        for _ in range(70):
            check_rate_limit(dummy_ip)
            record_request(dummy_ip, "/api/resource", "GET", blocked=is_banned(dummy_ip))
    return jsonify({"status": "simulated"})

@app.route('/health')
def health_check():
    return jsonify({"status": "OK"})

if __name__ == '__main__':
    print("=====================================================")
    print("  Unified DDoS System running on http://127.0.0.1:8080")
    print("=====================================================")
    app.run(host='0.0.0.0', port=8080, debug=True)
