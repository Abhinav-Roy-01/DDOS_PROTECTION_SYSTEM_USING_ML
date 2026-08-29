"""
Game CAPTCHA Module - Flask Blueprint Routes.

Provides a Dino-run style game CAPTCHA for suspicious IPs (ML score 0.44-0.72).
Uses HMAC-SHA256 for session integrity and Redis for state management.
"""

import hashlib
import hmac
import json
import os
import random
import string
import time
import logging

from flask import (
    Blueprint,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

import redis

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CAPTCHA_SECRET_KEY = os.environ.get("CAPTCHA_SECRET_KEY", "ddos-captcha-secret-key-change-in-production")
PARTIAL_TOKEN_SECRET = os.environ.get("PARTIAL_TOKEN_SECRET", "partial-token-secret-key-change-in-production")
FULL_TOKEN_SECRET = os.environ.get("FULL_TOKEN_SECRET", "full-token-secret-key-change-in-production")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_DB = int(os.environ.get("REDIS_DB", 0))

SCORE_THRESHOLD = 150
MAX_ATTEMPTS = 3
SESSION_TTL = 600        # 10 minutes (enough time to play)
VERIFIED_TTL = 3600      # 1 hour
BLOCKED_TTL = 86400      # 24 hours
ATTEMPTS_TTL = 900       # 15 minutes

# Behavior thresholds for bot detection
MIN_REACTION_TIME_MS = 50        # Humans can't react faster than ~50ms consistently
MAX_REACTION_VARIANCE = 5.0      # Bots have near-zero variance
MIN_JUMP_COUNT = 1               # Must have jumped at least once

logger = logging.getLogger("captcha")

# ---------------------------------------------------------------------------
# In-Memory Store (fallback when Redis is unavailable)
# ---------------------------------------------------------------------------

class InMemoryStore:
    """
    Drop-in replacement for Redis that stores data in memory.
    Used automatically when Redis is not available (development mode).
    Supports: get, set, setex, exists, delete, incr, expire, scan, ping, keys.
    """

    def __init__(self):
        self._data = {}
        self._expiry = {}
        logger.warning("Using IN-MEMORY store (Redis unavailable). Data is not persistent.")

    def _check_expiry(self, key):
        if key in self._expiry and time.time() > self._expiry[key]:
            self._data.pop(key, None)
            self._expiry.pop(key, None)
            return True
        return False

    def ping(self):
        return True

    def get(self, key):
        self._check_expiry(key)
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value

    def setex(self, key, ttl, value):
        self._data[key] = value
        self._expiry[key] = time.time() + ttl

    def exists(self, key):
        self._check_expiry(key)
        return 1 if key in self._data else 0

    def delete(self, *keys):
        for key in keys:
            self._data.pop(key, None)
            self._expiry.pop(key, None)

    def incr(self, key):
        self._check_expiry(key)
        val = self._data.get(key, "0")
        new_val = int(val) + 1
        self._data[key] = str(new_val)
        return new_val

    def expire(self, key, ttl):
        if key in self._data:
            self._expiry[key] = time.time() + ttl

    def scan(self, cursor, match="*", count=50):
        """Simulate Redis SCAN. Returns (0, matching_keys) — single pass."""
        import fnmatch
        pattern = match.replace("*", "**")  # fnmatch uses * differently
        matching = [k for k in self._data if fnmatch.fnmatch(k, match) and not self._check_expiry(k)]
        return (0, matching)

    def keys(self, pattern="*"):
        import fnmatch
        return [k for k in self._data if fnmatch.fnmatch(k, pattern) and not self._check_expiry(k)]


# ---------------------------------------------------------------------------
# Redis Client (lazy connection, auto-fallback to in-memory)
# ---------------------------------------------------------------------------

_redis_client = None


def get_redis():
    """Get or create Redis client. Falls back to InMemoryStore if Redis is unavailable."""
    global _redis_client
    if _redis_client is None:
        try:
            client = redis.StrictRedis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            _redis_client = client
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}), using in-memory store")
            _redis_client = InMemoryStore()
    return _redis_client


def redis_safe(func):
    """Decorator to handle storage errors gracefully."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Storage error: {e}")
            return jsonify({"status": "error", "message": "Internal server error"}), 500
    wrapper.__name__ = func.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------

def generate_game_id(length=16):
    """Generate cryptographically random game ID."""
    chars = string.ascii_letters + string.digits
    return "".join(random.SystemRandom().choice(chars) for _ in range(length))


def generate_hmac_secret(game_id):
    """Generate HMAC-SHA256 secret from game_id."""
    return hmac.new(
        CAPTCHA_SECRET_KEY.encode("utf-8"),
        game_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_partial_token(ip):
    """Generate partial token for client."""
    return hmac.new(
        PARTIAL_TOKEN_SECRET.encode("utf-8"),
        ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def generate_full_token(secret, partial_token):
    """Generate full verification token."""
    payload = f"{secret}:{partial_token}"
    return hmac.new(
        FULL_TOKEN_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_client_ip():
    """Extract real client IP from request headers."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


def analyze_behavior(behavior_data):
    """
    Analyze behavior data to detect bots.
    Returns (is_human: bool, reason: str).

    Checks: did the player actually interact with the match-3 game?
    If they reached the score threshold, they swapped candies — that's human behavior.
    """
    if not behavior_data or not isinstance(behavior_data, dict):
        logger.warning(f"Behavior check: missing data — {behavior_data}")
        return False, "missing_behavior_data"

    swap_count = behavior_data.get("swap_count", 0)
    input_device = behavior_data.get("input_device", "unknown")
    move_times = behavior_data.get("move_times", [])

    logger.info(
        f"Behavior data: swaps={swap_count}, device={input_device}, "
        f"move_times={len(move_times)} entries"
    )

    # Check 1: Must have made at least one valid swap
    if swap_count < 1:
        return False, "no_interaction (0 swaps)"

    # Check 2: Input device must be recognized
    if input_device not in ("keyboard", "touch", "mouse"):
        return False, "unknown_input_device"

    # Check 3: If enough move times, check for bot-like consistency
    if len(move_times) > 5:
        fast = sum(1 for t in move_times if t < MIN_REACTION_TIME_MS)
        if fast > len(move_times) * 0.8:
            return False, "superhuman_speed"

    return True, "passed"


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

captcha_bp = Blueprint(
    "captcha",
    __name__,
    template_folder="templates",
)


@captcha_bp.route("/captcha/new_game", methods=["GET"])
@redis_safe
def new_game():
    """
    Generate a new game session.

    Creates game_id + HMAC secret, stores in Redis with 5-min TTL.
    Returns JSON: {game_id, redirect_url}
    """
    r = get_redis()
    ip = get_client_ip()

    # Check if IP is already blocked
    if r.exists(f"captcha:blocked:{ip}"):
        return jsonify({
            "status": "blocked",
            "message": "Access denied. Your IP has been flagged.",
        }), 403

    # Check if IP is already verified
    if r.exists(f"captcha:verified:{ip}"):
        return jsonify({
            "status": "already_verified",
            "message": "You are already verified.",
        }), 200

    # Check attempt count
    attempts = r.get(f"captcha:attempts:{ip}")
    if attempts and int(attempts) >= MAX_ATTEMPTS:
        # Auto-block
        r.setex(
            f"captcha:blocked:{ip}",
            BLOCKED_TTL,
            json.dumps({
                "reason": "max_attempts_exceeded",
                "flagged_at": time.time(),
                "ip": ip,
            }),
        )
        return jsonify({
            "status": "blocked",
            "message": "Too many failed attempts. Access denied.",
        }), 403

    # Generate new game
    game_id = generate_game_id()
    secret = generate_hmac_secret(game_id)

    session_data = {
        "secret": secret,
        "ip": ip,
        "created_at": time.time(),
        "attempts": int(attempts) if attempts else 0,
    }

    r.setex(
        f"captcha:session:{game_id}",
        SESSION_TTL,
        json.dumps(session_data),
    )

    logger.info(f"New game created: {game_id} for IP: {ip}")

    # Auto-redirect to the challenge page
    return redirect(f"/captcha/challenge?game_id={game_id}")


@captcha_bp.route("/captcha/challenge", methods=["GET"])
@redis_safe
def challenge():
    """
    Serve the Dino Run game HTML page.

    Expects ?game_id=... query parameter. Validates session exists in Redis.
    """
    r = get_redis()
    game_id = request.args.get("game_id", "")
    ip = get_client_ip()

    if not game_id:
        return redirect(url_for("captcha.new_game"))

    # Check if blocked
    if r.exists(f"captcha:blocked:{ip}"):
        return render_template(
            "captcha_game.html",
            game_id="",
            game_state="blocked",
            error_message="Your IP has been blocked due to suspicious activity.",
        )

    # Validate session
    session_raw = r.get(f"captcha:session:{game_id}")
    if not session_raw:
        return redirect(url_for("captcha.new_game"))

    session_data = json.loads(session_raw)

    # Verify IP matches
    if session_data.get("ip") != ip:
        logger.warning(f"IP mismatch for game {game_id}: {session_data.get('ip')} vs {ip}")
        return redirect(url_for("captcha.new_game"))

    # Generate partial token for the client
    partial_token = generate_partial_token(ip)

    return render_template(
        "captcha_game.html",
        game_id=game_id,
        partial_token=partial_token,
        game_state="ready",
        error_message="",
    )


@captcha_bp.route("/captcha/verify", methods=["POST"])
@redis_safe
def verify():
    """
    Verify game completion.

    Expects JSON: {game_id, score, partial_token, behavior_data}
    Validates HMAC, score threshold, and behavior signals.
    On pass: generates full token, sets cookie, whitelists IP in Redis.
    """
    r = get_redis()
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status": "fail", "message": "Invalid request body"}), 400

    game_id = data.get("game_id", "")
    score = data.get("score", 0)
    partial_token = data.get("partial_token", "")
    behavior_data = data.get("behavior_data", {})

    # Validate session exists
    session_raw = r.get(f"captcha:session:{game_id}")
    if not session_raw:
        logger.warning(f"Session expired for game_id: {game_id}")
        return jsonify({"status": "expired", "message": "Session expired. Please start a new game."}), 400

    session_data = json.loads(session_raw)
    ip = get_client_ip()

    # Verify IP matches session
    if session_data.get("ip") != ip:
        logger.warning(f"Verify IP mismatch: {session_data.get('ip')} vs {ip}")
        return jsonify({"status": "fail", "message": "Session mismatch"}), 400

    # Verify HMAC - reconstruct expected secret
    expected_secret = generate_hmac_secret(game_id)
    if not hmac.compare_digest(expected_secret, session_data.get("secret", "")):
        logger.warning(f"HMAC verification failed for game {game_id}")
        return jsonify({"status": "fail", "message": "Security validation failed"}), 400

    # Verify partial token
    expected_partial = generate_partial_token(ip)
    if not hmac.compare_digest(expected_partial, partial_token):
        logger.warning(f"Partial token mismatch for game {game_id}")
        return jsonify({"status": "fail", "message": "Token validation failed"}), 400

    # Check score threshold
    if not isinstance(score, (int, float)) or score < SCORE_THRESHOLD:
        return jsonify({
            "status": "fail",
            "message": f"Score {int(score)} is below threshold ({SCORE_THRESHOLD})",
        }), 400

    # Analyze behavior data
    is_human, reason = analyze_behavior(behavior_data)
    if not is_human:
        logger.warning(f"Behavior analysis failed for {ip}: {reason}")
        # Don't immediately block — increment attempts instead
        attempts_key = f"captcha:attempts:{ip}"
        current = r.incr(attempts_key)
        if current == 1:
            r.expire(attempts_key, ATTEMPTS_TTL)

        if current >= MAX_ATTEMPTS:
            r.setex(
                f"captcha:blocked:{ip}",
                BLOCKED_TTL,
                json.dumps({
                    "reason": f"behavior_analysis_{reason}",
                    "flagged_at": time.time(),
                    "ip": ip,
                }),
            )
            return jsonify({
                "status": "blocked",
                "message": "Access denied due to suspicious behavior.",
            }), 403

        return jsonify({
            "status": "fail",
            "message": "Verification failed. Please try again.",
        }), 400

    # --- ALL CHECKS PASSED ---

    # Generate full verification token
    full_token = generate_full_token(session_data["secret"], partial_token)

    # Whitelist IP in Redis
    r.setex(
        f"captcha:verified:{ip}",
        VERIFIED_TTL,
        json.dumps({
            "token": full_token,
            "verified_at": time.time(),
            "expires": time.time() + VERIFIED_TTL,
            "game_id": game_id,
            "score": score,
        }),
    )

    # Clean up session
    r.delete(f"captcha:session:{game_id}")
    r.delete(f"captcha:attempts:{ip}")

    # Build response with cookie
    response = make_response(jsonify({
        "status": "pass",
        "message": "Verification successful. You are now whitelisted.",
        "token": full_token,
    }))

    response.set_cookie(
        "captcha_token",
        full_token,
        max_age=VERIFIED_TTL,
        httponly=True,
        samesite="Lax",
        secure=False,  # Set True in production with HTTPS
    )

    logger.info(f"IP verified: {ip} | game: {game_id} | score: {score}")

    return response, 200


@captcha_bp.route("/captcha/fail", methods=["POST"])
@redis_safe
def fail():
    """
    Handle game failure (all lives lost).

    Increments failure counter. If count >= 3, blocks IP and redirects to honeypot.
    """
    r = get_redis()
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"status": "error", "message": "Invalid request"}), 400

    game_id = data.get("game_id", "")
    ip = get_client_ip()

    # Validate session
    session_raw = r.get(f"captcha:session:{game_id}")
    if session_raw:
        session_data = json.loads(session_raw)
        if session_data.get("ip") != ip:
            return jsonify({"status": "error", "message": "Session mismatch"}), 400
    else:
        # Session expired, use IP from request
        pass

    # Increment attempt counter
    attempts_key = f"captcha:attempts:{ip}"
    current_attempts = r.incr(attempts_key)
    if current_attempts == 1:
        r.expire(attempts_key, ATTEMPTS_TTL)

    # Clean up old session
    if game_id:
        r.delete(f"captcha:session:{game_id}")

    if current_attempts >= MAX_ATTEMPTS:
        # Block the IP
        r.setex(
            f"captcha:blocked:{ip}",
            BLOCKED_TTL,
            json.dumps({
                "reason": "too_many_failed_attempts",
                "flagged_at": time.time(),
                "ip": ip,
                "total_attempts": current_attempts,
            }),
        )

        logger.warning(f"IP blocked after {current_attempts} attempts: {ip}")

        return jsonify({
            "status": "blocked",
            "message": "Too many failed attempts. Access denied for 24 hours.",
            "attempts": current_attempts,
            "redirect": "/honeypot",
        }), 403

    # Allow retry - generate new game ID
    new_game_id = generate_game_id()
    new_secret = generate_hmac_secret(new_game_id)

    r.setex(
        f"captcha:session:{new_game_id}",
        SESSION_TTL,
        json.dumps({
            "secret": new_secret,
            "ip": ip,
            "created_at": time.time(),
            "attempts": current_attempts,
        }),
    )

    logger.info(f"Retry granted for IP {ip} (attempt {current_attempts}/{MAX_ATTEMPTS})")

    return jsonify({
        "status": "retry",
        "message": f"Attempt {current_attempts}/{MAX_ATTEMPTS}. Try again.",
        "attempts": current_attempts,
        "max_attempts": MAX_ATTEMPTS,
        "new_game_id": new_game_id,
        "redirect_url": f"/captcha/challenge?game_id={new_game_id}",
    }), 200


# ---------------------------------------------------------------------------
# Honeypot endpoint (placeholder - integrate with existing system)
# ---------------------------------------------------------------------------

@captcha_bp.route("/honeypot", methods=["GET"])
def honeypot():
    """Honeypot page for blocked IPs — logs bot activity."""
    ip = get_client_ip()
    logger.warning(f"Honeypot accessed by: {ip}")
    return jsonify({
        "status": "ok",
        "message": "Request processed successfully.",
    }), 200


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from flask import Flask

    app = Flask(__name__)
    app.register_blueprint(captcha_bp)

    logging.basicConfig(level=logging.INFO)

    print("=" * 60)
    print("  GAME CAPTCHA MODULE")
    print("=" * 60)
    print(f"  Redis:  {REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
    print(f"  Server: http://127.0.0.1:5000")
    print("=" * 60)

    app.run(host="127.0.0.1", port=5000, debug=True)
