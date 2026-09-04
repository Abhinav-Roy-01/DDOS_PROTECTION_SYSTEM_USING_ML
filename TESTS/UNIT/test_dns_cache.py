"""
TESTS/UNIT/test_dns_cache.py
Tests CORE/CACHE/dns_cache.py directly, plus one integration-style test
against a live resolver.py process to confirm the full miss -> hit ->
correct-response-ID pipeline works end to end.

The roundtrip/hit tests need a real Redis running (they use flushall to
start from a clean slate) -- they're skipped automatically if Redis isn't
reachable, rather than failing, since not everyone runs Redis locally at
all times during development.

Run:
    pytest TESTS/UNIT/test_dns_cache.py -v
"""

import os
import sys
import time
import subprocess

import pytest

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_here, "..", "..", "CORE", "CACHE"))
import dns_cache


def _redis_available():
    try:
        import redis
        redis.Redis(socket_connect_timeout=0.5).ping()
        return True
    except Exception:
        return False


REDIS_UP = _redis_available()
requires_redis = pytest.mark.skipif(not REDIS_UP, reason="Redis is not running locally")


@pytest.fixture(autouse=True)
def clean_cache():
    if REDIS_UP:
        import redis
        redis.Redis().flushall()
    yield


# --- pure logic, no Redis needed -----------------------------------------

def test_cache_key_format():
    assert dns_cache._cache_key("Google.com.", "A") == "dns_cache:Google.com.:A"


def test_extract_min_ttl_picks_the_shortest():
    import dns.rrset
    import dns.rdataclass
    import dns.rdatatype

    class FakeRRset:
        def __init__(self, ttl):
            self.ttl = ttl

    class FakeResponse:
        answer = [FakeRRset(300), FakeRRset(60), FakeRRset(120)]

    assert dns_cache.extract_min_ttl(FakeResponse()) == 60


def test_extract_min_ttl_with_no_answers_falls_back_to_min_ttl():
    class EmptyResponse:
        answer = []

    assert dns_cache.extract_min_ttl(EmptyResponse()) == dns_cache.MIN_TTL


def test_get_returns_none_and_store_does_not_crash_when_redis_unreachable(monkeypatch):
    """Simulates Redis being down regardless of whether it's actually
    running on this machine -- the resolver must never crash because
    the cache is unavailable."""
    monkeypatch.setattr(dns_cache, "_get_client", lambda: None)
    assert dns_cache.get_cached_response("anything.com.", "A") is None
    dns_cache.store_response("anything.com.", "A", b"bytes", 300)  # must not raise


# --- requires a real Redis ------------------------------------------------

@requires_redis
def test_store_then_get_roundtrip_returns_exact_bytes():
    dns_cache.store_response("roundtrip-test.com.", "A", b"exact-bytes-123", 120)
    result = dns_cache.get_cached_response("roundtrip-test.com.", "A")
    assert result == b"exact-bytes-123"


@requires_redis
def test_ttl_is_clamped_to_min_ttl_floor():
    import redis
    dns_cache.store_response("floor-test.com.", "A", b"x", 2)  # below MIN_TTL
    actual_ttl = redis.Redis().ttl(dns_cache._cache_key("floor-test.com.", "A"))
    assert actual_ttl > 0
    assert actual_ttl <= dns_cache.MIN_TTL + 1  # +1 tolerance for timing


@requires_redis
def test_ttl_is_clamped_to_max_ttl_ceiling():
    import redis
    dns_cache.store_response("ceiling-test.com.", "A", b"x", 999999)  # above MAX_TTL
    actual_ttl = redis.Redis().ttl(dns_cache._cache_key("ceiling-test.com.", "A"))
    assert actual_ttl <= dns_cache.MAX_TTL
    assert actual_ttl > dns_cache.MAX_TTL - 5  # should be close to the ceiling, not near 0


@requires_redis
def test_miss_before_store_then_hit_after():
    assert dns_cache.get_cached_response("fresh-domain.com.", "A") is None
    dns_cache.store_response("fresh-domain.com.", "A", b"payload", 60)
    assert dns_cache.get_cached_response("fresh-domain.com.", "A") == b"payload"


# --- full pipeline integration test, real resolver process ---------------

@requires_redis
def test_resolver_cache_hit_has_correct_response_id():
    """This is the regression test for the actual bug found during manual
    testing: a naive cache would replay the ORIGINAL query's ID, which a
    real client (using a fresh random ID per query, per RFC 1035 and as a
    spoofing defense) correctly rejects. Runs a real resolver.py process
    and sends two distinct queries with different random IDs.

    Startup timing note: spawning a Python subprocess that imports redis +
    dnspython and binds a UDP socket takes a different amount of time on
    different machines/OSes (Windows subprocess + first-run antivirus
    scanning can be noticeably slower than Linux). Rather than hardcode a
    sleep duration that works on one machine and times out on another,
    this retries the first query for up to ~8s until the resolver is
    actually ready to answer, instead of gambling on a fixed delay.
    """
    import dns.message
    import dns.query
    import dns.exception

    resolver_path = os.path.join(_here, "..", "..", "CORE", "DNS-RESOLVER", "resolver.py")
    proc = subprocess.Popen(
        [sys.executable, resolver_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        r1 = None
        q1 = None
        deadline = time.time() + 8
        last_error = None
        while time.time() < deadline:
            if proc.poll() is not None:
                # process already exited -- it crashed on startup, not a timing issue
                out, err = proc.communicate()
                pytest.fail(f"resolver.py exited early (code {proc.returncode}).\nstdout:\n{out}\nstderr:\n{err}")
            try:
                q1 = dns.message.make_query("github.com.", "A")
                r1 = dns.query.udp(q1, "127.0.0.1", port=15353, timeout=1)
                break  # got a real response, resolver is ready
            except (dns.exception.Timeout, OSError) as e:
                last_error = e
                time.sleep(0.3)
        if r1 is None:
            proc.terminate()
            out, err = proc.communicate(timeout=3)
            pytest.fail(
                f"resolver never answered within 8s (last query error: {last_error}).\n"
                f"Process was still running (not crashed). stdout:\n{out}\nstderr:\n{err}"
            )

        q2 = dns.message.make_query("github.com.", "A")  # different random ID
        r2 = dns.query.udp(q2, "127.0.0.1", port=15353, timeout=3)  # should be cache HIT

        assert q1.id != q2.id, "test is invalid if dnspython happened to reuse the same ID"
        assert r1.id == q1.id
        assert r2.id == q2.id, "cache hit returned a response with the WRONG query ID"
        assert [str(a) for a in r1.answer] == [str(a) for a in r2.answer]
    finally:
        proc.terminate()
        proc.wait(timeout=3)