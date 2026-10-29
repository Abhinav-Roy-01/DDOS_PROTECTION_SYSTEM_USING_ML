"""Store verified, privacy-preserving feedback in shared Redis state."""

import hashlib
import hmac
import ipaddress
import json
import math
import os
import time
from numbers import Real

import RATE_LIMITER
from ML_ENGINE import FEATURES, validate_features

PENDING_PREFIX = "SHIELD:PENDING:"
HUMAN_KEY = "SHIELD:FEEDBACK:HUMAN"
BOT_KEY = "SHIELD:FEEDBACK:BOT"
AUDIT_KEY = "SHIELD:FEEDBACK:AUDIT"
DROPPED_KEY = "SHIELD:FBDROPPED"
CHALLENGE_PREFIX = "captcha:required:"
MAX_FEEDBACK_ROWS = 50_000
MAX_AUDIT_ROWS = 20_000
MAX_ROWS_PER_RETRAIN = 2_000
PER_IP_DAILY_CAP = 3
PER_SUBNET_DAILY_CAP = 10
COUNTER_TTL_SECONDS = 86_400
PENDING_TTL_SECONDS = 3_600
MIN_SOLVE_SECONDS = 3
MAX_SOLVE_SECONDS = 120

LABEL_KEYS = {"human": HUMAN_KEY, "bot": BOT_KEY}


class FeedbackConfigurationError(RuntimeError):
    """Raised when the privacy-preserving feedback hash key is unavailable."""


def _client():
    """Return the shared Redis connection configured by the API."""
    return RATE_LIMITER.get_redis_client()


def _canonical_ip(ip):
    """Validate and normalize an IP address for short-lived Redis keys."""
    return str(ipaddress.ip_address(ip))


def _ip_hash(ip):
    """Return the first 16 HMAC-SHA256 hex characters for an IP address."""
    secret = os.environ.get("FEEDBACK_HASH_KEY", "").encode("utf-8")
    if len(secret) < 32:
        raise FeedbackConfigurationError("FEEDBACK_HASH_KEY must contain at least 32 bytes.")
    return hmac.new(secret, ip.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def _push_capped(client, key, value, max_rows):
    """Append one JSON value and keep the Redis list within its configured cap."""
    pipeline = client.pipeline(transaction=True)
    pipeline.lpush(key, json.dumps(value, separators=(",", ":"), sort_keys=True))
    pipeline.ltrim(key, 0, max_rows - 1)
    pipeline.execute()


def _audit(client, label, hashed_ip, source, accepted, reason):
    """Append a bounded audit entry without storing a raw IP or request value."""
    entry = {
        "ts": time.time(),
        "label": label,
        "ip_hash": hashed_ip,
        "source": source,
        "accepted": bool(accepted),
        "reason": reason,
    }
    _push_capped(client, AUDIT_KEY, entry, MAX_AUDIT_ROWS)


def _counter_key(label, kind, value):
    """Build the expiring counter key for one IP or subnet and label."""
    return f"SHIELD:FBCOUNT:{label}:{kind}:{value}"


def _increment_counter(client, key):
    """Increment a daily feedback cap counter and set its first-use expiry."""
    count = client.incr(key)
    if count == 1:
        client.expire(key, COUNTER_TTL_SECONDS)
    return count


def _read_pending(client, ip, label, source, hashed_ip):
    """Read and decode the latest pending feature vector for an IP."""
    raw = client.get(PENDING_PREFIX + ip)
    if raw is None:
        _audit(client, label, hashed_ip, source, False, "no_pending")
        return None
    try:
        pending = json.loads(raw)
    except (ValueError, TypeError):
        _audit(client, label, hashed_ip, source, False, "invalid_pending")
        return None
    if not isinstance(pending, dict) or not isinstance(pending.get("features"), dict):
        _audit(client, label, hashed_ip, source, False, "invalid_pending")
        return None
    return pending


def _cap_rejection(client, label, ip, subnet, hashed_ip, source):
    """Apply per-IP and per-subnet caps and audit the first exceeded limit."""
    ip_count = _increment_counter(client, _counter_key(label, "IP", ip))
    subnet_count = _increment_counter(client, _counter_key(label, "SUBNET", subnet))
    if ip_count > PER_IP_DAILY_CAP:
        client.incr(DROPPED_KEY)
        _audit(client, label, hashed_ip, source, False, "ip_cap")
        return True
    if subnet_count > PER_SUBNET_DAILY_CAP:
        client.incr(DROPPED_KEY)
        _audit(client, label, hashed_ip, source, False, "subnet_cap")
        return True
    return False


def record_pending(ip, features, session_id=None):
    """Store the latest validated feature vector under a short-lived IP key."""
    normalized_ip = _canonical_ip(ip)
    if session_id is not None and (
        not isinstance(session_id, str) or len(session_id) > 128
    ):
        raise ValueError("session_id must be a string of at most 128 characters.")
    payload = {
        "features": validate_features(features),
        "ts": time.time(),
        "session_id": session_id,
    }
    _client().set(
        PENDING_PREFIX + normalized_ip,
        json.dumps(payload, separators=(",", ":"), sort_keys=True),
        ex=PENDING_TTL_SECONDS,
    )


def _label_pending(ip, label, source):
    """Apply the shared cap, audit, and append logic for a verified outcome."""
    normalized_ip = _canonical_ip(ip)
    client = _client()
    hashed_ip = _ip_hash(normalized_ip)
    pending = _read_pending(client, normalized_ip, label, source, hashed_ip)
    if pending is None:
        return False

    network = ipaddress.ip_network(
        f"{normalized_ip}/{24 if ipaddress.ip_address(normalized_ip).version == 4 else 48}",
        strict=False,
    )
    if _cap_rejection(client, label, normalized_ip, str(network), hashed_ip, source):
        client.delete(PENDING_PREFIX + normalized_ip)
        return False

    row = {
        "features": {name: pending["features"][name] for name in FEATURES},
        "ts": pending["ts"],
        "ip_hash": hashed_ip,
        "source": source,
    }
    _push_capped(client, LABEL_KEYS[label], row, MAX_FEEDBACK_ROWS)
    _audit(client, label, hashed_ip, source, True, "accepted")
    client.delete(PENDING_PREFIX + normalized_ip)
    return True


def label_as_bot(ip):
    """Label one fresh pending vector as bot after an ML-score ban."""
    return _label_pending(ip, "bot", "score_ban")


def label_as_human(ip, solve_seconds):
    """Label a challenged IP as human after a plausible CAPTCHA solve."""
    normalized_ip = _canonical_ip(ip)
    client = _client()
    hashed_ip = _ip_hash(normalized_ip)
    if (
        isinstance(solve_seconds, bool)
        or not isinstance(solve_seconds, Real)
        or not math.isfinite(float(solve_seconds))
        or not MIN_SOLVE_SECONDS <= float(solve_seconds) <= MAX_SOLVE_SECONDS
    ):
        _audit(client, "human", hashed_ip, "captcha_pass", False, "solve_time")
        return False
    if not client.exists(CHALLENGE_PREFIX + normalized_ip):
        _audit(client, "human", hashed_ip, "captcha_pass", False, "not_challenged")
        return False
    return _label_pending(normalized_ip, "human", "captcha_pass")


def pending_count():
    """Count currently unexpired pending feature vectors in shared Redis."""
    return sum(1 for _ in _client().scan_iter(match=PENDING_PREFIX + "*"))


def feedback_counts():
    """Return pending, labeled, and cap-dropped feedback totals."""
    client = _client()
    return {
        "pending": pending_count(),
        "human": client.llen(HUMAN_KEY),
        "bot": client.llen(BOT_KEY),
        "dropped": int(client.get(DROPPED_KEY) or 0),
    }


def _export_label(client, label):
    """Atomically move one live feedback list to its inflight export key."""
    live_key = LABEL_KEYS[label]
    inflight_key = f"{live_key}:INFLIGHT"
    count_key = f"{inflight_key}:COUNT"
    if client.exists(inflight_key):
        raise RuntimeError(f"A {label} feedback export is already in progress.")
    if client.exists(live_key):
        client.rename(live_key, inflight_key)
    rows = client.lrange(inflight_key, 0, MAX_ROWS_PER_RETRAIN - 1)
    client.set(count_key, len(rows))
    return [json.loads(row) for row in rows]


def export_for_training():
    """Move feedback lists to inflight keys and return at most 2000 rows per label."""
    client = _client()
    human_rows = _export_label(client, "human")
    bot_rows = _export_label(client, "bot")
    return human_rows, bot_rows


def _restore_inflight(client, label, consume_export):
    """Commit consumed rows or restore all rows when a retrain does not deploy."""
    live_key = LABEL_KEYS[label]
    inflight_key = f"{live_key}:INFLIGHT"
    count_key = f"{inflight_key}:COUNT"
    consumed = int(client.get(count_key) or 0) if consume_export else 0
    remaining = client.lrange(inflight_key, consumed, -1)
    pipeline = client.pipeline(transaction=True)
    if remaining:
        pipeline.lpush(live_key, *reversed(remaining))
        pipeline.ltrim(live_key, 0, MAX_FEEDBACK_ROWS - 1)
    pipeline.delete(inflight_key, count_key)
    pipeline.execute()


def commit_export():
    """Remove exported rows after successful deployment and retain any overflow."""
    client = _client()
    _restore_inflight(client, "human", True)
    _restore_inflight(client, "bot", True)


def abort_export():
    """Restore all exported rows after a failed or rejected retraining run."""
    client = _client()
    _restore_inflight(client, "human", False)
    _restore_inflight(client, "bot", False)
