"""
CACHE/dns_cache.py
Redis-backed DNS response cache, sitting in front of the upstream forward
in resolver.py.

Design:
  - Key:   dns_cache:<domain>:<qtype>   e.g. dns_cache:google.com.:A
  - Value: raw wire-format response bytes (no re-parsing needed on a hit)
  - TTL:   read from the real answer's own TTL, not a fixed number --
           so we never serve a record past when the authoritative
           server said it's valid
  - If Redis is unreachable, cache calls fail soft (return None / no-op)
    rather than crashing the resolver -- same pattern already used in
    HTTP-LAYER-SHIELD/CAPTCHA/captcha_routes.py's InMemoryStore fallback.

Target: sub-5ms cache hit latency.
"""

import logging

import redis
import dns.message

log = logging.getLogger("dns-cache")

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
MIN_TTL = 30       # never cache shorter than this (avoids thrashing on 0/1s TTLs)
MAX_TTL = 3600      # never cache longer than this (1 hour), even if upstream says more

_client = None


def _get_client():
    """Lazy connection, reused across calls. Returns None if Redis is down
    so callers can fail soft instead of crashing the resolver."""
    global _client
    if _client is None:
        try:
            _client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, socket_connect_timeout=0.5)
            _client.ping()
            log.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            log.warning(f"Redis unavailable ({e}) -- DNS caching disabled, all queries will forward upstream")
            _client = False  # sentinel: "we already tried and it's down"
    return _client if _client else None


def _cache_key(domain: str, qtype: str) -> str:
    return f"dns_cache:{domain}:{qtype}"


def get_cached_response(domain: str, qtype: str) -> bytes | None:
    """Returns raw wire-format bytes if cached and not expired, else None."""
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(_cache_key(domain, qtype))
    except Exception as e:
        log.warning(f"Cache read failed: {e}")
        return None


def store_response(domain: str, qtype: str, wire_bytes: bytes, answer_ttl: int) -> None:
    """Caches a response for min(max(answer_ttl, MIN_TTL), MAX_TTL) seconds."""
    client = _get_client()
    if client is None:
        return
    ttl = max(MIN_TTL, min(answer_ttl, MAX_TTL))
    try:
        client.set(_cache_key(domain, qtype), wire_bytes, ex=ttl)
    except Exception as e:
        log.warning(f"Cache write failed: {e}")


def extract_min_ttl(response: dns.message.Message) -> int:
    """Real DNS answers can carry multiple records with different TTLs --
    always cache for the SHORTEST one, so we never hold a record longer
    than any individual answer said we're allowed to."""
    ttls = [rrset.ttl for rrset in response.answer]
    return min(ttls) if ttls else MIN_TTL