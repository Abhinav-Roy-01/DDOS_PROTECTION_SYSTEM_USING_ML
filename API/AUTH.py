"""
AUTH.PY -- Admin key check for the /api/* routes.

PHASE: 1
There is NO hardcoded fallback key. If ADMIN_API_KEY is not set in the
environment (.env), admin routes refuse to work instead of using a default.
"""

import hmac
import os
from functools import wraps

from flask import jsonify, request


def get_admin_key():
    """Returns ADMIN_API_KEY from the environment, or None if it is not set."""
    return os.environ.get("ADMIN_API_KEY") or None


def is_valid_admin_key(provided):
    """Compare a supplied admin key with the configured server key."""
    expected = get_admin_key()
    return expected is not None and hmac.compare_digest(
        str(provided).encode(),
        expected.encode(),
    )


def require_admin_key(view):
    """Decorator for admin routes. The caller must send the key in the
    X-Admin-Key header. Returns 503 if no key is configured on the server,
    401 if the key is missing or wrong."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        expected = get_admin_key()
        if expected is None:
            return jsonify({"error": "Admin key is not configured on the server."}), 503

        provided = request.headers.get("X-Admin-Key", "")
        if not is_valid_admin_key(provided):
            return jsonify({"error": "Invalid or missing admin key."}), 401

        return view(*args, **kwargs)
    return wrapper