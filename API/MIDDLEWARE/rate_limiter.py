"""
MIDDLEWARE/rate_limiter.py
Per-IP rate limiting for DNS-layer API using Redis sliding window.
See HTTP-LAYER-SHIELD/API/rate_limiter.py for the HTTP-layer equivalent
(in-memory ban list + request logging), which predates this DNS-layer version.
"""
