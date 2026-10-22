"""
TEST_RATE_LIMITER.PY -- tests for API/RATE_LIMITER.py (Redis-backed).

Uses fakeredis, so no real Redis server is needed to run these.
Run from the project root:
    pytest TESTS/TEST_RATE_LIMITER.py -v
"""

import os
import sys

import fakeredis
import pytest
import redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "API"))

import RATE_LIMITER as RL


@pytest.fixture
def clock(monkeypatch):
    """Controllable fake clock: clock.now is the current epoch time."""
    class Clock:
        now = 1_000_000.0
    monkeypatch.setattr(RL, "_now", lambda: Clock.now)
    return Clock


@pytest.fixture(autouse=True)
def fresh_redis():
    """Every test gets a brand-new empty fake Redis."""
    client = fakeredis.FakeRedis(decode_responses=True)
    RL.set_redis_client(client)
    yield client
    RL.set_redis_client(None)


# --- RATE LIMITING ---------------------------------------------------------

def test_requests_under_limit_are_allowed(clock):
    for _ in range(RL.RATE_LIMIT):
        assert RL.check_rate_limit("1.1.1.1") is True


def test_request_over_limit_is_rejected(clock):
    for _ in range(RL.RATE_LIMIT):
        RL.check_rate_limit("1.1.1.1")
    assert RL.check_rate_limit("1.1.1.1") is False


def test_limit_is_per_ip(clock):
    for _ in range(RL.RATE_LIMIT + 5):
        RL.check_rate_limit("1.1.1.1")
    assert RL.check_rate_limit("2.2.2.2") is True


def test_window_slides_so_old_requests_stop_counting(clock):
    for _ in range(RL.RATE_LIMIT):
        RL.check_rate_limit("1.1.1.1")
    clock.now += RL.RATE_WINDOW + 1
    assert RL.check_rate_limit("1.1.1.1") is True


def test_reaching_ban_threshold_bans_the_ip(clock):
    for _ in range(RL.BAN_THRESHOLD):
        RL.check_rate_limit("3.3.3.3")
    assert RL.is_banned("3.3.3.3") is True


# --- BAN LIST ---------------------------------------------------------------

def test_unknown_ip_is_not_banned(clock):
    assert RL.is_banned("9.9.9.9") is False


def test_manual_ban_and_unban(clock):
    RL.manual_ban("4.4.4.4")
    assert RL.is_banned("4.4.4.4") is True
    assert RL.manual_unban("4.4.4.4") is True
    assert RL.is_banned("4.4.4.4") is False


def test_unban_of_unbanned_ip_returns_false(clock):
    assert RL.manual_unban("5.5.5.5") is False


def test_ban_expires_after_ban_duration(clock):
    RL.manual_ban("6.6.6.6")
    clock.now += RL.BAN_DURATION + 1
    assert RL.is_banned("6.6.6.6") is False


# --- SHARED STATE ACROSS WORKERS (the reason for using Redis) ---------------

def test_ban_is_visible_to_a_second_worker():
    server = fakeredis.FakeServer()
    worker_one = fakeredis.FakeRedis(server=server, decode_responses=True)
    worker_two = fakeredis.FakeRedis(server=server, decode_responses=True)

    RL.set_redis_client(worker_one)
    RL.manual_ban("7.7.7.7")

    RL.set_redis_client(worker_two)
    assert RL.is_banned("7.7.7.7") is True


# --- LOGGING + DASHBOARD READS ----------------------------------------------

def test_stats_count_allowed_and_blocked_requests(clock):
    RL.record_request("1.1.1.1", "/predict", "POST", blocked=False)
    RL.record_request("1.1.1.1", "/predict", "POST", blocked=True, ml_verdict="bot", ml_score=-0.2)
    RL.record_request("2.2.2.2", "/health", "GET")

    stats = RL.get_stats()
    assert stats["total_requests"] == 3
    assert stats["blocked_requests"] == 1
    assert stats["allowed_requests"] == 2
    assert stats["unique_ips"] == 2
    assert stats["top_ips"]["1.1.1.1"] == 2
    assert stats["top_blocked_ips"] == {"1.1.1.1": 1}


def test_request_log_is_capped(clock, monkeypatch):
    monkeypatch.setattr(RL, "MAX_LOG", 5)
    for i in range(8):
        RL.record_request(f"10.0.0.{i}", "/x", "GET")
    assert RL.get_stats()["total_requests"] == 5


def test_stats_list_banned_ips(clock):
    RL.manual_ban("8.8.8.8")
    stats = RL.get_stats()
    assert stats["banned_ips"] == 1
    assert stats["banned_list"][0]["ip"] == "8.8.8.8"


def test_matrix_shape_and_threat_levels(clock):
    RL.record_request("1.1.1.1", "/p", "POST", blocked=False)
    RL.record_request("2.2.2.2", "/p", "POST", blocked=True)
    RL.manual_ban("3.3.3.3")
    RL.record_request("3.3.3.3", "/p", "POST", blocked=True)

    matrix = RL.get_matrix()
    assert len(matrix["timeline"]) == 60
    threat = {row["ip"]: row["threat"] for row in matrix["ip_matrix"]}
    assert threat["1.1.1.1"] == "low"
    assert threat["2.2.2.2"] == "medium"
    assert threat["3.3.3.3"] == "critical"


def test_click_feed_is_newest_first_and_respects_limit(clock):
    for i in range(5):
        RL.record_click({"click_count": i})
    feed = RL.get_click_feed(limit=3)
    assert [c["click_count"] for c in feed] == [4, 3, 2]


# --- STARTUP + FAILURE POLICY -------------------------------------------------

def test_init_records_start_time_once(clock):
    RL.init_rate_limiter()
    clock.now += 100
    RL.init_rate_limiter()
    assert RL.get_stats()["uptime_sec"] == 100


class BrokenRedis:
    """Stand-in client where every call fails like a dead Redis server."""
    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise redis.exceptions.ConnectionError("redis is down")
        return fail


def test_request_path_fails_open_when_redis_is_down():
    RL.set_redis_client(BrokenRedis())
    assert RL.check_rate_limit("1.1.1.1") is True
    assert RL.is_banned("1.1.1.1") is False
    RL.record_request("1.1.1.1", "/x", "GET")   # must not raise
    RL.manual_ban("1.1.1.1")                    # must not raise


def test_init_raises_when_redis_is_unreachable():
    RL.set_redis_client(BrokenRedis())
    with pytest.raises(redis.exceptions.ConnectionError):
        RL.init_rate_limiter()