"""
API/auth.py
API-key authentication for the admin/control routes under /api/.

Why an API key and not JWT/OAuth: this is a single-admin local dashboard,
not a multi-user public service -- a shared secret checked on every
request is the right amount of complexity here, not a full auth system.

Design:
  - The key comes from the ADMIN_API_KEY environment variable.
  - The server injects that SAME key into the dashboard page it renders
    (see server.py's "/" route), so your own browser's dashboard.js can
    attach it automatically -- but anyone hitting these routes directly,
    without ever having loaded the dashboard from this server, can't.
  - Comparison uses hmac.compare_digest, not ==, to avoid leaking the
    key's value through response-timing differences (a timing attack).

If ADMIN_API_KEY is never set, a random one is generated at startup and
printed once to the console -- so the server is never accidentally left
wide open, but also never crashes just because a .env wasn't configured.
"""

import os
import secrets
import hmac
import logging
from functools import wraps

from flask import request, jsonify

log = logging.getLogger("auth")

_ADMIN_API_KEY = os.environ.get("ADMIN_API_KEY")
if not _ADMIN_API_KEY:
    _ADMIN_API_KEY = secrets.token_hex(16)
    log.warning(
        "ADMIN_API_KEY not set in environment -- generated a random one for "
        "this run only. Set ADMIN_API_KEY in your .env for a stable key "
        f"across restarts. Generated key: {_ADMIN_API_KEY}"
    )


def get_admin_key() -> str:
    """Used by server.py to inject the key into the rendered dashboard page."""
    return _ADMIN_API_KEY


def require_admin_key(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        provided = request.headers.get("X-Admin-Key", "")
        if not hmac.compare_digest(provided, _ADMIN_API_KEY):
            return jsonify({"error": "Unauthorized -- missing or invalid X-Admin-Key header"}), 401
        return view_func(*args, **kwargs)
    return wrapped