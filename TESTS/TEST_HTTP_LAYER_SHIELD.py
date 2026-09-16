"""
TEST_HTTP_LAYER_SHIELD.PY -- core API test suite.

PHASE: 1 (rebuild for Redis-backed rate limiter)
REUSE: copy from old project's TESTS/test_http_layer_shield.py, update
       any test that asserts on in-memory rate_limiter state to instead
       assert against Redis (or a fakeredis instance for test isolation).

NOT YET IMPLEMENTED.
"""
