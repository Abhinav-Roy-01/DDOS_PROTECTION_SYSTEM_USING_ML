"""
AUTH.PY -- Admin key generation/verification for /api/* routes.

PHASE: 1 (basic) -> 3 (hardening: remove any dev fallback, .env only)
REUSE: rebuilt from old project's API/auth.py -- see DOCS/REUSE_MAP.md

WHAT GOES HERE:
    - get_admin_key() -- reads ADMIN_API_KEY from environment, NO hardcoded
      fallback value (Phase 3 requirement -- old project had a dev fallback,
      this rebuild must not)
    - require_admin_key -- decorator checking X-Admin-Key header

NOT YET IMPLEMENTED.
"""
