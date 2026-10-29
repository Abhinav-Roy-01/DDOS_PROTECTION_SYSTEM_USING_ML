"""
SERVER.PY -- Main Flask application.

PHASE: 1 (base wiring). Later phases add /predict (Phase 2), CAPTCHA (Phase 2),
retrain routes (Phase 4).

WHAT IT DOES NOW:
    - Requests use either the public or allowlisted-admin Redis rate bucket.
    - Every request is logged for the dashboard stats.
    - Admin routes (/api/*) need the X-Admin-Key header.

RUN LOCALLY (needs Redis running):
    python API/SERVER.py
RUN WITH GUNICORN (Linux / WSL):
    gunicorn --chdir API "SERVER:create_app()" -w 4 -b 127.0.0.1:8080

ENV VARS (put them in .env at the repo root):
    ADMIN_API_KEY        required for admin routes
    ADMIN_IP_ALLOWLIST   comma-separated IPs/CIDRs for admin and local source access
    REDIS_URL            default redis://localhost:6379/0
    PORT                 dev server port for `python API/SERVER.py`, default 8080
    TRUSTED_PROXY_COUNT  how many proxies (nginx etc.) sit in front of this app.
                         Default 0. Set to 1 behind nginx so the real client IP
                         is read from X-Forwarded-For. Keep 0 when there is no
                         proxy, otherwise anyone can fake their IP.
"""

import ipaddress
import logging
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from redis.exceptions import RedisError
from werkzeug.middleware.proxy_fix import ProxyFix

import RATE_LIMITER
from AUTH import require_admin_key

# Paths that skip the rate limiter and the request log (uptime monitors).
EXEMPT_PATHS = {"/health"}
logger = logging.getLogger(__name__)


def add_project_paths():
    """Make sibling project modules importable in script and gunicorn modes."""
    project_root = Path(__file__).resolve().parents[1]
    root_path = str(project_root)
    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    for folder in ("API", "CAPTCHA", "DASHBOARD", "FEEDBACK", "DEMO-APP"):
        folder_path = str(project_root / folder)
        if folder_path not in sys.path:
            sys.path.insert(0, folder_path)


def _parse_admin_allowlist():
    """Parse the explicit source-IP networks trusted for admin access."""
    configured = os.environ.get(
        "ADMIN_IP_ALLOWLIST",
        "127.0.0.1/32,::1/128",
    )
    try:
        return tuple(
            ipaddress.ip_network(entry.strip(), strict=False)
            for entry in configured.split(",")
            if entry.strip()
        )
    except ValueError as error:
        raise ValueError("ADMIN_IP_ALLOWLIST must contain valid IPs or CIDRs.") from error


def _get_ip_from_body(allow_ipv6_subnet=False):
    """Reads {"ip": "..."} from the JSON body. Returns the IP string if it is a
    valid IPv4/IPv6 address, otherwise None."""
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()
    try:
        return str(ipaddress.ip_address(ip))
    except ValueError:
        if allow_ipv6_subnet:
            try:
                network = ipaddress.ip_network(ip, strict=False)
            except ValueError:
                return None
            if network.version == 6 and network.prefixlen == 64:
                return str(network)
        return None


def create_app():
    """Builds and returns the Flask app. Raises if Redis is unreachable, so a
    bad REDIS_URL is caught at startup instead of at the first request."""
    load_dotenv()
    add_project_paths()
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

    # Behind nginx every request arrives from 127.0.0.1. ProxyFix makes
    # request.remote_addr the real client IP, but only if we are told how many
    # proxies to trust.
    proxy_count = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
    if proxy_count > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count)

    RATE_LIMITER.init_rate_limiter()
    RATE_LIMITER.configure_admin_allowlist(_parse_admin_allowlist())
    from CAPTCHA_ROUTES import captcha_bp
    from DASHBOARD_ROUTES import dashboard_bp
    from DEMO_ROUTES import demo_bp

    app.register_blueprint(demo_bp)
    app.register_blueprint(captcha_bp)
    app.register_blueprint(dashboard_bp)

    @app.before_request
    def check_ban_and_rate_limit():
        """Runs before every route. Banned IPs get 403, IPs over the rate limit
        get 429. Returning a response here stops the route from running."""
        g.request_id = uuid.uuid4().hex
        if request.path in EXEMPT_PATHS:
            return None

        ip = request.remote_addr
        if RATE_LIMITER.is_admin_ip_allowlisted(ip):
            if not RATE_LIMITER.check_admin_rate_limit(ip):
                g.blocked = True
                response = jsonify({"status": "rate_limited", "message": "Too many admin requests."})
                response.status_code = 429
                response.headers["Retry-After"] = str(RATE_LIMITER.RATE_WINDOW)
                return response
            return None

        if RATE_LIMITER.is_banned(ip):
            g.blocked = True
            return jsonify({"status": "blocked", "message": "IP is banned."}), 403

        if not RATE_LIMITER.check_rate_limit(ip):
            g.blocked = True
            response = jsonify({"status": "rate_limited", "message": "Too many requests."})
            response.status_code = 429
            response.headers["Retry-After"] = str(RATE_LIMITER.RATE_WINDOW)
            return response

        if request.path.startswith("/api/"):
            g.blocked = True
            return jsonify({"status": "admin_ip_not_allowed"}), 403

        return None

    @app.after_request
    def log_request(response):
        """Runs after every response (including the blocked ones above) and
        stores one entry in the request log for the dashboard."""
        if request.path not in EXEMPT_PATHS:
            RATE_LIMITER.record_request(
                request.remote_addr, request.path, request.method,
                blocked=g.get("blocked", False),
                ml_verdict=g.get("ml_verdict"),
                ml_score=g.get("ml_score"),
                request_id=g.get("request_id"),
                status_code=response.status_code,
            )
        response.headers["X-Request-ID"] = g.get("request_id", uuid.uuid4().hex)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'self'; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
            "object-src 'none'; script-src 'self'; style-src 'self'"
        )
        return response

    @app.route("/health")
    def health():
        """Liveness check for monitors and nginx."""
        return jsonify({"status": "OK"})

    @app.route("/ready")
    def readiness():
        """Report whether Redis and a verified model can serve predictions."""
        try:
            RATE_LIMITER.get_redis_client().ping()
        except RedisError:
            return jsonify({
                "status": "not_ready",
                "redis": "unavailable",
                "model": "unknown",
            }), 503

        from DEMO_ROUTES import _get_engine

        model_status = _get_engine().get_status()
        ready = not model_status["degraded"]
        response = jsonify({
            "status": "ready" if ready else "not_ready",
            "redis": "available",
            "model": "ready" if ready else "degraded",
            "model_version": model_status["model_version"],
        })
        return response, 200 if ready else 503

    @app.route("/api/stats")
    @require_admin_key
    def api_stats():
        """Aggregate request statistics for the dashboard."""
        return jsonify(RATE_LIMITER.get_stats())

    @app.route("/api/matrix")
    @require_admin_key
    def api_matrix():
        """Per-second timeline and per-IP threat matrix for the dashboard."""
        return jsonify(RATE_LIMITER.get_matrix())

    @app.route("/api/overview")
    @require_admin_key
    def api_overview():
        """Return aggregate ML, feedback, counter, and histogram data."""
        from DEMO_ROUTES import _get_engine
        from FEEDBACK_STORE import feedback_counts

        model_status = _get_engine().get_status()
        return jsonify({
            "counters": RATE_LIMITER.get_counters(),
            "score_histogram": RATE_LIMITER.get_score_histogram(),
            "model": model_status,
            "feedback": feedback_counts(),
        })

    @app.route("/api/messages")
    @require_admin_key
    def api_messages():
        """Return a bounded list of verified contact messages to administrators."""
        try:
            limit = int(request.args.get("limit", "20"))
        except ValueError:
            return jsonify({"status": "invalid_request", "message": "limit must be an integer."}), 400
        if not 1 <= limit <= 50:
            return jsonify({"status": "invalid_request", "message": "limit must be between 1 and 50."}), 400
        return jsonify({"messages": RATE_LIMITER.get_messages(limit)})

    @app.route("/api/feedback/stats")
    @require_admin_key
    def api_feedback_stats():
        """Return aggregate verified-feedback counts."""
        from FEEDBACK_STORE import feedback_counts

        return jsonify(feedback_counts())

    @app.route("/api/retrain/start", methods=["POST"])
    @require_admin_key
    def api_retrain_start():
        """Run an administrator-triggered quality-gated retraining job."""
        from RETRAIN_RUNNER import start_retrain

        if request.mimetype != "application/json":
            return jsonify({
                "status": "invalid_request",
                "message": "Use application/json.",
            }), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({
                "status": "invalid_request",
                "message": "Body must be a JSON object.",
            }), 400
        dry_run = payload.get("dry_run", False)
        if not isinstance(dry_run, bool):
            return jsonify({
                "status": "invalid_request",
                "message": "'dry_run' must be a boolean.",
            }), 400
        result, status_code = start_retrain(dry_run=dry_run)
        return jsonify(result), status_code

    @app.route("/api/retrain/status")
    @require_admin_key
    def api_retrain_status():
        """Return shared status for the latest retraining job."""
        from RETRAIN_RUNNER import get_retrain_status

        return jsonify(get_retrain_status())

    @app.route("/api/ban", methods=["POST"])
    @require_admin_key
    def api_ban():
        """Bans the IP given in the JSON body: {"ip": "1.2.3.4"}."""
        ip = _get_ip_from_body()
        if ip is None:
            return jsonify({"error": "Body must be JSON with a valid 'ip'."}), 400
        if RATE_LIMITER.is_admin_ip_allowlisted(ip):
            return jsonify({
                "status": "refused",
                "message": "Allowlisted admin addresses cannot be banned.",
            }), 409
        RATE_LIMITER.manual_ban(ip)
        return jsonify({"status": "banned", "ip": ip})

    @app.route("/api/unban", methods=["POST"])
    @require_admin_key
    def api_unban():
        """Removes the ban on the IP given in the JSON body."""
        ip = _get_ip_from_body(allow_ipv6_subnet=True)
        if ip is None:
            return jsonify({"error": "Body must be JSON with a valid 'ip'."}), 400
        was_banned = RATE_LIMITER.manual_unban(ip)
        return jsonify({"status": "unbanned" if was_banned else "not_banned", "ip": ip})

    @app.errorhandler(404)
    def not_found(error):
        del error
        return jsonify({"status": "not_found", "message": "Route not found."}), 404

    @app.errorhandler(413)
    def request_too_large(error):
        del error
        return jsonify({"status": "request_too_large"}), 413

    @app.errorhandler(500)
    def internal_error(error):
        logger.exception(
            "Unhandled request error request_id=%s error_type=%s",
            g.get("request_id"),
            type(error).__name__,
        )
        return jsonify({
            "status": "internal_error",
            "request_id": g.get("request_id"),
        }), 500

    return app


if __name__ == "__main__":
    # Development server only. Production uses gunicorn (see top of file).
    app = create_app()  # also loads .env
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))