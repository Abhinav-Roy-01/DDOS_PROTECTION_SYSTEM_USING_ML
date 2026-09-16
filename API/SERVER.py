"""
SERVER.PY -- Main Flask application.

PHASE: 1 (base wiring) -> 2 (DEMO-APP wiring) -> 3 (hardening)
REUSE: rebuilt from old project's API/server.py -- see DOCS/REUSE_MAP.md

WHAT GOES HERE:
    - Flask app init, CORS
    - before_request: rate-limit + ban check (via RATE_LIMITER.py, Redis-backed)
    - /predict route -- calls ML_ENGINE.predict(), routes to allow/captcha/block
      using thresholds from ML/MODELS/THRESHOLDS.json
    - /health, /stats, /matrix routes
    - /api/* admin routes (ban, retrain trigger, feedback stats, model reload)
      -- protected by AUTH.require_admin_key, restricted to admin IP at nginx layer (Phase 3)
    - Registers CAPTCHA_ROUTES blueprint
    - Served by gunicorn in production (see INFRA/DEPLOY.md), NOT app.run(debug=True)

NOT YET IMPLEMENTED.
"""
