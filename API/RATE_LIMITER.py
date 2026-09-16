"""
RATE_LIMITER.PY -- Per-IP rate limiting and ban list.

PHASE: 1 (this is the REBUILD, not a copy -- see DOCS/REUSE_MAP.md)
REUSE: same interface as old project's API/rate_limiter.py, but Redis-backed
       instead of in-process dicts.

WHY REDIS, NOT A PYTHON DICT:
    gunicorn runs multiple worker processes. An in-memory dict means each
    worker has its OWN rate limits and ban list -- an IP banned on worker 1
    sails through worker 2. Redis gives all workers a shared, consistent view.

WHAT GOES HERE:
    - check_rate_limit(ip) -> bool          (Redis INCR + EXPIRE sliding window)
    - record_request(ip, path, method, ...)  (Redis-backed request log, capped size)
    - is_banned(ip) -> bool                  (Redis SET membership / key existence)
    - manual_ban(ip)                         (Redis SET with TTL)
    - get_stats(), get_matrix()              (aggregate reads from Redis)
    - record_click(data), get_click_feed()   (Redis list, capped, for dashboard telemetry)

NOT YET IMPLEMENTED.
"""
