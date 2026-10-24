"""
SERVER.PY -- Main Flask application.

PHASE: 1 (base wiring). Later phases add /predict (Phase 2), CAPTCHA (Phase 2),
retrain routes (Phase 4).

WHAT IT DOES NOW:
    - Every request (except /health) is checked against the Redis-backed ban
      list and rate limiter before the route runs.
    - Every request is logged for the dashboard stats.
    - Admin routes (/api/*) need the X-Admin-Key header.

RUN LOCALLY (needs Redis running):
    python API/SERVER.py
RUN WITH GUNICORN (Linux / WSL):
    gunicorn --chdir API "SERVER:create_app()" -w 4 -b 127.0.0.1:8080

ENV VARS (put them in .env at the repo root):
    ADMIN_API_KEY        required for admin routes
    REDIS_URL            default redis://localhost:6379/0
    PORT                 dev server port for `python API/SERVER.py`, default 8080
    TRUSTED_PROXY_COUNT  how many proxies (nginx etc.) sit in front of this app.
                         Default 0. Set to 1 behind nginx so the real client IP
                         is read from X-Forwarded-For. Keep 0 when there is no
                         proxy, otherwise anyone can fake their IP.
"""

import ipaddress
import os

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

import RATE_LIMITER
from AUTH import require_admin_key

# Paths that skip the rate limiter and the request log (uptime monitors).
EXEMPT_PATHS = {"/health"}


def _get_ip_from_body():
    """Reads {"ip": "..."} from the JSON body. Returns the IP string if it is a
    valid IPv4/IPv6 address, otherwise None."""
    data = request.get_json(silent=True) or {}
    ip = str(data.get("ip", "")).strip()
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return None
    return ip


def create_app():
    """Builds and returns the Flask app. Raises if Redis is unreachable, so a
    bad REDIS_URL is caught at startup instead of at the first request."""
    load_dotenv()
    app = Flask(__name__)

    # Behind nginx every request arrives from 127.0.0.1. ProxyFix makes
    # request.remote_addr the real client IP, but only if we are told how many
    # proxies to trust.
    proxy_count = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
    if proxy_count > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=proxy_count)

    RATE_LIMITER.init_rate_limiter()

    @app.before_request
    def check_ban_and_rate_limit():
        """Runs before every route. Banned IPs get 403, IPs over the rate limit
        get 429. Returning a response here stops the route from running."""
        if request.path in EXEMPT_PATHS:
            return None

        ip = request.remote_addr
        if RATE_LIMITER.is_banned(ip):
            g.blocked = True
            return jsonify({"status": "blocked", "message": "IP is banned."}), 403

        if not RATE_LIMITER.check_rate_limit(ip):
            g.blocked = True
            response = jsonify({"status": "rate_limited", "message": "Too many requests."})
            response.status_code = 429
            response.headers["Retry-After"] = str(RATE_LIMITER.RATE_WINDOW)
            return response

        return None

    @app.after_request
    def log_request(response):
        """Runs after every response (including the blocked ones above) and
        stores one entry in the request log for the dashboard."""
        if request.path not in EXEMPT_PATHS:
            RATE_LIMITER.record_request(
                request.remote_addr, request.path, request.method,
                blocked=g.get("blocked", False),
            )
        return response

    @app.route("/health")
    def health():
        """Liveness check for monitors and nginx."""
        return jsonify({"status": "OK"})

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

    @app.route("/api/ban", methods=["POST"])
    @require_admin_key
    def api_ban():
        """Bans the IP given in the JSON body: {"ip": "1.2.3.4"}."""
        ip = _get_ip_from_body()
        if ip is None:
            return jsonify({"error": "Body must be JSON with a valid 'ip'."}), 400
        RATE_LIMITER.manual_ban(ip)
        return jsonify({"status": "banned", "ip": ip})

    @app.route("/api/unban", methods=["POST"])
    @require_admin_key
    def api_unban():
        """Removes the ban on the IP given in the JSON body."""
        ip = _get_ip_from_body()
        if ip is None:
            return jsonify({"error": "Body must be JSON with a valid 'ip'."}), 400
        was_banned = RATE_LIMITER.manual_unban(ip)
        return jsonify({"status": "unbanned" if was_banned else "not_banned", "ip": ip})

    return app


if __name__ == "__main__":
    # Development server only. Production uses gunicorn (see top of file).
    app = create_app()  # also loads .env
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8080")))