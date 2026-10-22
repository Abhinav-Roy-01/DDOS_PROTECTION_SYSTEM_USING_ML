"""
RATE_LIMITER.PY -- Per-IP rate limiting, ban list, and request/click logs.

PHASE: 1
REPLACES: old in-memory rate_limiter.py (same function names, same return shapes)

WHY REDIS:
    gunicorn runs several worker processes. Python dicts are per-process, so
    an IP banned on worker 1 would still pass on worker 2. Every piece of
    state here lives in Redis so all workers share one view.

REDIS KEYS:
    SHIELD:RATE:<ip>        sorted set  - request timestamps (sliding window)
    SHIELD:BANNED           sorted set  - ip -> ban expiry (epoch seconds)
    SHIELD:LOG:REQUESTS     list        - recent request entries (newest first)
    SHIELD:LOG:CLICKS       list        - recent telemetry entries (newest first)
    SHIELD:START_TIME       string      - when the shield first started

FAILURE POLICY:
    If Redis is down, the request-path functions FAIL OPEN (allow the request,
    log a warning) so a Redis outage never takes the whole site down. nginx
    rate limiting (INFRA/NGINX) is still active in that case.
"""

import functools
import json
import logging
import os
import time
import uuid
from collections import Counter
from datetime import datetime

import redis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

RATE_LIMIT = 30         # max requests per IP per RATE_WINDOW seconds
RATE_WINDOW = 10        # sliding window length in seconds
BAN_THRESHOLD = 60      # requests inside one window that trigger an auto-ban
BAN_DURATION = 300      # seconds an IP stays banned
MAX_LOG = 2000         # max stored request log entries
MAX_CLICK_LOG = 5000    # max stored click/telemetry entries

DEFAULT_REDIS_URL = "redis://localhost:6379/0"

KEY_RATE = "SHIELD:RATE:"
KEY_BANNED = "SHIELD:BANNED"
KEY_REQUEST_LOG = "SHIELD:LOG:REQUESTS"
KEY_CLICK_LOG = "SHIELD:LOG:CLICKS"
KEY_START_TIME = "SHIELD:START_TIME"

_client = None


# ---------------------------------------------------------------------------
# INTERNAL HELPERS
# ---------------------------------------------------------------------------

def _now():
    """Current time in epoch seconds. Single place to patch in tests."""
    return time.time()


def _get_client():
    """Returns the shared Redis client, creating it on first use. The short
    timeouts make a dead Redis fail fast instead of hanging requests."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            os.environ.get("REDIS_URL", DEFAULT_REDIS_URL),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


def set_redis_client(client):
    """Replaces the shared Redis client. Used by tests to inject fakeredis."""
    global _client
    _client = client


def _fail_open(default):
    """Decorator: if Redis raises, log a warning and return `default`
    instead of crashing the request."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except redis.exceptions.RedisError as error:
                logger.warning("Redis unavailable in %s: %s", func.__name__, error)
                return default
        return wrapper
    return decorator


def _push_capped(key, entry, max_len):
    """Pushes a JSON entry to the front of a Redis list and trims the list
    to max_len, so memory use stays bounded."""
    pipe = _get_client().pipeline()
    pipe.lpush(key, json.dumps(entry, default=str))
    pipe.ltrim(key, 0, max_len - 1)
    pipe.execute()


def _read_log(key):
    """Reads a whole log list and returns entries oldest -> newest."""
    raw = _get_client().lrange(key, 0, -1)
    return [json.loads(item) for item in raw][::-1]


def _get_banned():
    """Removes expired bans, then returns {ip: ban_expiry_epoch}."""
    client = _get_client()
    client.zremrangebyscore(KEY_BANNED, "-inf", _now())
    return dict(client.zrange(KEY_BANNED, 0, -1, withscores=True))


def _get_uptime():
    """Seconds since the shield first started (0 if start time not recorded)."""
    start = _get_client().get(KEY_START_TIME)
    return int(_now() - float(start)) if start else 0


# ---------------------------------------------------------------------------
# STARTUP
# ---------------------------------------------------------------------------

def init_rate_limiter():
    """Call once at app startup. Pings Redis (raises if unreachable, so a bad
    REDIS_URL is caught at boot) and records the start time if not yet set."""
    client = _get_client()
    client.ping()
    client.set(KEY_START_TIME, _now(), nx=True)


# ---------------------------------------------------------------------------
# BAN LIST
# ---------------------------------------------------------------------------

@_fail_open(False)
def is_banned(ip):
    """True if the IP has an unexpired ban. Expired bans are cleaned up here."""
    client = _get_client()
    until = client.zscore(KEY_BANNED, ip)
    if until is None:
        return False
    if until > _now():
        return True
    client.zrem(KEY_BANNED, ip)
    return False


@_fail_open(None)
def manual_ban(ip):
    """Bans an IP for BAN_DURATION seconds."""
    _get_client().zadd(KEY_BANNED, {ip: _now() + BAN_DURATION})


def manual_unban(ip):
    """Removes a ban. Returns True if the IP was banned."""
    return _get_client().zrem(KEY_BANNED, ip) > 0


# ---------------------------------------------------------------------------
# RATE LIMITING
# ---------------------------------------------------------------------------

@_fail_open(True)
def check_rate_limit(ip):
    """Records this request in the IP's sliding window and returns True if the
    request is allowed. Returns False when the IP is over RATE_LIMIT, and also
    bans the IP once it reaches BAN_THRESHOLD requests inside one window."""
    client = _get_client()
    now = _now()
    key = KEY_RATE + ip

    pipe = client.pipeline(transaction=True)
    pipe.zremrangebyscore(key, 0, now - RATE_WINDOW)
    pipe.zadd(key, {f"{now:.6f}-{uuid.uuid4().hex[:8]}": now})
    pipe.zcard(key)
    pipe.expire(key, RATE_WINDOW + 1)
    _, _, count, _ = pipe.execute()

    if count >= BAN_THRESHOLD:
        manual_ban(ip)
        return False
    return count <= RATE_LIMIT


# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------

@_fail_open(None)
def record_request(ip, path, method, blocked=False, ml_verdict=None, ml_score=None):
    """Stores one request entry (used by the dashboard stats)."""
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "ip": ip,
        "path": path,
        "method": method,
        "blocked": blocked,
        "ml_verdict": ml_verdict,
        "ml_score": ml_score,
    }
    _push_capped(KEY_REQUEST_LOG, entry, MAX_LOG)


@_fail_open(None)
def record_click(data):
    """Stores one behavioral telemetry entry (mouse/click/keystroke features)."""
    entry = {"time": datetime.now().isoformat(timespec="milliseconds"), **data}
    _push_capped(KEY_CLICK_LOG, entry, MAX_CLICK_LOG)


def get_click_feed(limit=50):
    """Most recent telemetry entries, newest first (dashboard live panel)."""
    raw = _get_client().lrange(KEY_CLICK_LOG, 0, limit - 1)
    return [json.loads(item) for item in raw]


# ---------------------------------------------------------------------------
# DASHBOARD READS
# ---------------------------------------------------------------------------

def get_stats():
    """Aggregate numbers for the dashboard: totals, top IPs/paths, bans."""
    logs = _read_log(KEY_REQUEST_LOG)
    bans = _get_banned()

    total = len(logs)
    blocked = sum(1 for r in logs if r.get("blocked"))

    ip_counts = Counter(r["ip"] for r in logs)
    path_counts = Counter(r["path"] for r in logs)
    blocked_ip_counts = Counter(r["ip"] for r in logs if r.get("blocked"))

    now = datetime.now()
    recent = [r for r in logs if (now - datetime.fromisoformat(r["time"])).total_seconds() < 60]

    return {
        "total_requests": total,
        "allowed_requests": total - blocked,
        "blocked_requests": blocked,
        "unique_ips": len(ip_counts),
        "banned_ips": len(bans),
        "uptime_sec": _get_uptime(),
        "req_per_sec": round(len(recent) / 60, 2),
        "top_ips": dict(ip_counts.most_common(10)),
        "top_paths": dict(path_counts.most_common(10)),
        "top_blocked_ips": dict(blocked_ip_counts.most_common(5)),
        "recent_requests": logs[-50:],
        "banned_list": [
            {"ip": ip, "until": datetime.fromtimestamp(ts).isoformat()}
            for ip, ts in bans.items()
        ],
    }


def get_matrix():
    """Per-second timeline (last 60s) and per-IP threat matrix for the dashboard."""
    logs = _read_log(KEY_REQUEST_LOG)
    bans = _get_banned()
    now = datetime.now()

    # Per-second timeline: key 60 = this second, key 1 = 59 seconds ago.
    timeline = {}
    for r in logs:
        try:
            age = int((now - datetime.fromisoformat(r["time"])).total_seconds())
            if 0 <= age < 60:
                slot = timeline.setdefault(60 - age, {"allowed": 0, "blocked": 0})
                slot["blocked" if r.get("blocked") else "allowed"] += 1
        except Exception:
            pass

    timeline_arr = [
        {"sec": k, **timeline.get(k, {"allowed": 0, "blocked": 0})}
        for k in range(1, 61)
    ]

    # Per-IP threat matrix.
    ip_counts = Counter(r["ip"] for r in logs)
    ip_blocked = Counter(r["ip"] for r in logs if r.get("blocked"))
    ip_matrix = []
    for ip, total in ip_counts.most_common(20):
        blk = ip_blocked.get(ip, 0)
        threat = ("critical" if ip in bans else
                  "high" if blk > 10 else
                  "medium" if blk > 0 else "low")
        ip_matrix.append({
            "ip": ip, "total": total,
            "blocked": blk, "allowed": total - blk,
            "threat": threat, "banned": ip in bans,
        })

    return {
        "timestamp": now.isoformat(),
        "timeline": timeline_arr,
        "ip_matrix": ip_matrix,
        "summary": {
            "total": len(logs),
            "blocked": sum(1 for r in logs if r.get("blocked")),
            "banned": len(bans),
            "uptime": _get_uptime(),
        },
    }