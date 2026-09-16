"""
CAPTCHA_ROUTES.PY -- game-based CAPTCHA blueprint for suspicious IPs.

PHASE: 2 (base) -> 3 (hardening: secrets to .env, secure=True cookies)
REUSE: rebuilt from old project's CAPTCHA/captcha_routes.py -- see
       DOCS/REUSE_MAP.md. Logic is the same; hardening changes:
         - CAPTCHA_SECRET_KEY / PARTIAL_TOKEN_SECRET / FULL_TOKEN_SECRET
           must come from .env with NO hardcoded fallback
         - verify() cookie must be secure=True (HTTPS-only) once deployed

WHAT GOES HERE:
    - Dino-run style game CAPTCHA, HMAC-signed session tokens
    - /captcha/new_game, /captcha/verify routes
    - On verify() success: calls FEEDBACK_STORE.label_as_human(ip)

NOT YET IMPLEMENTED.
"""
