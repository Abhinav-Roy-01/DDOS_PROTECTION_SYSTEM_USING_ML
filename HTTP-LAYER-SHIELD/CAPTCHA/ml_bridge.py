"""
ML Bridge — CAPTCHA Status Checker.

Provides check_captcha_status(ip) for middleware.py to query
whether an IP has been verified, is pending challenge, or is blocked.
"""

import json
import logging

import redis

logger = logging.getLogger("captcha.ml_bridge")

# ---------------------------------------------------------------------------
# Redis Configuration (mirrors captcha_routes.py)
# ---------------------------------------------------------------------------

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0

_redis_client = None


def _get_redis():
    """Lazy-initialize Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.StrictRedis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis_client


# ---------------------------------------------------------------------------
# Public API — called by middleware.py
# ---------------------------------------------------------------------------

def check_captcha_status(ip):
    """
    Check the CAPTCHA verification status of an IP address.

    Returns one of:
        "blocked"   — IP is flagged as bot / too many failed attempts
        "verified"  — IP has passed the game CAPTCHA (whitelisted)
        "pending"   — IP has an active game session (currently playing)
        "unknown"   — No CAPTCHA data exists for this IP

    Redis key check order:  blocked → verified → pending → unknown
    """
    try:
        r = _get_redis()

        # 1. Check blocked list (highest priority)
        blocked_key = f"captcha:blocked:{ip}"
        if r.exists(blocked_key):
            data = r.get(blocked_key)
            if data:
                try:
                    info = json.loads(data)
                    logger.info(f"IP {ip} is BLOCKED — reason: {info.get('reason', 'unknown')}")
                except json.JSONDecodeError:
                    pass
            return "blocked"

        # 2. Check verified list
        verified_key = f"captcha:verified:{ip}"
        if r.exists(verified_key):
            data = r.get(verified_key)
            if data:
                try:
                    info = json.loads(data)
                    # Verify the token hasn't logically expired (double-check)
                    import time
                    expires = info.get("expires", 0)
                    if expires > 0 and time.time() > expires:
                        r.delete(verified_key)
                        logger.info(f"IP {ip} verification expired, removed key")
                        return "unknown"
                except (json.JSONDecodeError, ValueError):
                    pass
            logger.info(f"IP {ip} is VERIFIED")
            return "verified"

        # 3. Check for pending game sessions
        #    We scan for any captcha:session:* that belongs to this IP
        #    This is a lightweight cursor scan with a match pattern
        cursor = 0
        while True:
            cursor, keys = r.scan(cursor, match="captcha:session:*", count=50)
            for key in keys:
                session_data = r.get(key)
                if session_data:
                    try:
                        info = json.loads(session_data)
                        if info.get("ip") == ip:
                            logger.info(f"IP {ip} has PENDING captcha session: {key}")
                            return "pending"
                    except (json.JSONDecodeError, ValueError):
                        continue
            if cursor == 0:
                break

        # 4. No data found
        return "unknown"

    except redis.ConnectionError:
        logger.error(f"Redis connection error while checking IP {ip}")
        return "unknown"
    except redis.TimeoutError:
        logger.error(f"Redis timeout while checking IP {ip}")
        return "unknown"
    except Exception as e:
        logger.error(f"Unexpected error checking captcha status for {ip}: {e}")
        return "unknown"


def get_captcha_token(ip):
    """
    Retrieve the full CAPTCHA token for a verified IP.

    Returns the token string or None if not verified.
    """
    try:
        r = _get_redis()
        verified_key = f"captcha:verified:{ip}"
        data = r.get(verified_key)
        if data:
            info = json.loads(data)
            return info.get("token")
    except Exception as e:
        logger.error(f"Error getting captcha token for {ip}: {e}")
    return None


def is_ip_blocked(ip):
    """Quick check if IP is blocked. Returns bool."""
    try:
        r = _get_redis()
        return r.exists(f"captcha:blocked:{ip}") > 0
    except Exception:
        return False


def is_ip_verified(ip):
    """Quick check if IP is verified. Returns bool."""
    try:
        r = _get_redis()
        return r.exists(f"captcha:verified:{ip}") > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Optional: standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    test_ip = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    status = check_captcha_status(test_ip)
    print(f"CAPTCHA status for {test_ip}: {status}")
