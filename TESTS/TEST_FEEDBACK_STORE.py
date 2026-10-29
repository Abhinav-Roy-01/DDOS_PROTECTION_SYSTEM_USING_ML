"""Tests for Redis-backed feedback labels, caps, privacy, and exports."""

import json
import os
import sys

import fakeredis
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "API"))

from FEEDBACK import FEEDBACK_STORE
import RATE_LIMITER

FEATURES = {
    "click_count": 8,
    "avg_click_interval": 900.0,
    "click_interval_variance": 200_000.0,
    "click_interval_entropy": 1.5,
    "mouse_velocity_variance": 0.3,
    "max_element_click_rate": 1.2,
    "scroll_events": 4,
    "keystroke_count": 5,
}


@pytest.fixture(autouse=True)
def isolated_redis(monkeypatch):
    """Reset shared Redis and install a test-only feedback hash key."""
    RATE_LIMITER.set_redis_client(fakeredis.FakeRedis(decode_responses=True))
    monkeypatch.setenv("FEEDBACK_HASH_KEY", "feedback-test-secret-" + ("y" * 32))
    yield
    RATE_LIMITER.set_redis_client(None)


def _prepare_pending(ip):
    """Store one fresh test feature vector for a selected client IP."""
    FEEDBACK_STORE.record_pending(ip, FEATURES)


def test_pending_vector_has_redis_ttl_and_counts_shared_keys():
    """Pending vectors use Redis TTL and are counted while they exist."""
    _prepare_pending("192.0.2.1")
    client = RATE_LIMITER.get_redis_client()

    assert FEEDBACK_STORE.pending_count() == 1
    assert 0 < client.ttl("SHIELD:PENDING:192.0.2.1") <= FEEDBACK_STORE.PENDING_TTL_SECONDS
    client.delete("SHIELD:PENDING:192.0.2.1")
    assert FEEDBACK_STORE.pending_count() == 0
    assert FEEDBACK_STORE.label_as_bot("192.0.2.1") is False


def test_bot_feedback_contains_only_hashed_ip_after_ml_ban():
    """A score-ban label stores features and an HMAC hash, never a raw IP."""
    ip = "192.0.2.4"
    _prepare_pending(ip)

    assert FEEDBACK_STORE.label_as_bot(ip) is True
    row = json.loads(RATE_LIMITER.get_redis_client().lindex(FEEDBACK_STORE.BOT_KEY, 0))
    stored_values = json.dumps(row)
    assert row["source"] == "score_ban"
    assert row["ip_hash"] != ip
    assert ip not in stored_values
    audit = json.loads(
        RATE_LIMITER.get_redis_client().lindex(FEEDBACK_STORE.AUDIT_KEY, 0)
    )
    assert ip not in json.dumps(audit)
    assert FEEDBACK_STORE.pending_count() == 0


def test_human_feedback_requires_challenge_and_plausible_solve_time():
    """Only a challenged IP with a fresh vector and valid duration is labeled."""
    ip = "192.0.2.5"
    _prepare_pending(ip)
    assert FEEDBACK_STORE.label_as_human(ip, 10) is False

    client = RATE_LIMITER.get_redis_client()
    client.set(FEEDBACK_STORE.CHALLENGE_PREFIX + ip, "1", ex=3600)
    assert FEEDBACK_STORE.label_as_human(ip, 2.9) is False
    assert FEEDBACK_STORE.label_as_human(ip, 10) is True
    row = json.loads(client.lindex(FEEDBACK_STORE.HUMAN_KEY, 0))
    assert row["source"] == "captcha_pass"
    assert ip not in json.dumps(row)


@pytest.mark.parametrize("solve_seconds", [float("nan"), float("inf"), 2, 121, True])
def test_invalid_captcha_solve_durations_are_rejected(solve_seconds):
    """Invalid or out-of-range CAPTCHA durations cannot become human labels."""
    ip = "192.0.2.6"
    _prepare_pending(ip)
    RATE_LIMITER.get_redis_client().set(
        FEEDBACK_STORE.CHALLENGE_PREFIX + ip,
        "1",
        ex=3600,
    )

    assert FEEDBACK_STORE.label_as_human(ip, solve_seconds) is False


def test_per_ip_daily_cap_is_enforced():
    """At most three bot rows from one IP are accepted per 24-hour window."""
    ip = "192.0.2.7"
    accepted = []
    for _ in range(FEEDBACK_STORE.PER_IP_DAILY_CAP + 1):
        _prepare_pending(ip)
        accepted.append(FEEDBACK_STORE.label_as_bot(ip))

    assert accepted == [True, True, True, False]
    assert FEEDBACK_STORE.feedback_counts()["dropped"] == 1


def test_per_subnet_daily_cap_is_enforced():
    """The subnet limit applies across different IPv4 clients."""
    accepted = []
    for suffix in range(1, FEEDBACK_STORE.PER_SUBNET_DAILY_CAP + 2):
        ip = f"198.51.100.{suffix}"
        _prepare_pending(ip)
        accepted.append(FEEDBACK_STORE.label_as_bot(ip))

    assert accepted.count(True) == FEEDBACK_STORE.PER_SUBNET_DAILY_CAP
    assert accepted[-1] is False


def test_ipv6_feedback_caps_use_a_slash_48_subnet():
    """IPv6 addresses are grouped by their /48 for subnet label caps."""
    accepted = []
    for suffix in range(1, FEEDBACK_STORE.PER_SUBNET_DAILY_CAP + 2):
        ip = f"2001:db8:1234:{suffix:x}::1"
        _prepare_pending(ip)
        accepted.append(FEEDBACK_STORE.label_as_bot(ip))

    assert accepted.count(True) == FEEDBACK_STORE.PER_SUBNET_DAILY_CAP
    assert accepted[-1] is False


def test_export_abort_restores_feedback_without_losing_new_rows():
    """Aborting an export returns inflight and concurrently added rows."""
    _prepare_pending("203.0.113.1")
    assert FEEDBACK_STORE.label_as_bot("203.0.113.1") is True
    human_rows, bot_rows = FEEDBACK_STORE.export_for_training()
    _prepare_pending("203.0.113.2")
    assert FEEDBACK_STORE.label_as_bot("203.0.113.2") is True

    FEEDBACK_STORE.abort_export()

    assert human_rows == []
    assert len(bot_rows) == 1
    assert RATE_LIMITER.get_redis_client().llen(FEEDBACK_STORE.BOT_KEY) == 2


def test_commit_export_consumes_only_exported_rows_and_retains_overflow():
    """Successful export commit removes the batch and leaves later rows live."""
    _prepare_pending("203.0.113.3")
    FEEDBACK_STORE.label_as_bot("203.0.113.3")
    exported_humans, exported_bots = FEEDBACK_STORE.export_for_training()
    _prepare_pending("203.0.113.4")
    FEEDBACK_STORE.label_as_bot("203.0.113.4")

    FEEDBACK_STORE.commit_export()

    assert exported_humans == []
    assert len(exported_bots) == 1
    assert RATE_LIMITER.get_redis_client().llen(FEEDBACK_STORE.BOT_KEY) == 1


def test_export_limits_batch_size_per_label():
    """A training export never returns more than the configured maximum."""
    client = RATE_LIMITER.get_redis_client()
    rows = [json.dumps({"row": index}) for index in range(FEEDBACK_STORE.MAX_ROWS_PER_RETRAIN + 1)]
    client.rpush(FEEDBACK_STORE.BOT_KEY, *rows)

    _, bot_rows = FEEDBACK_STORE.export_for_training()

    assert len(bot_rows) == FEEDBACK_STORE.MAX_ROWS_PER_RETRAIN
    FEEDBACK_STORE.abort_export()
    assert client.llen(FEEDBACK_STORE.BOT_KEY) == len(rows)


def test_feedback_counts_and_shared_worker_visibility():
    """Multiple workers connected to the same Redis server see the same rows."""
    shared_server = fakeredis.FakeServer()
    worker_one = fakeredis.FakeRedis(server=shared_server, decode_responses=True)
    worker_two = fakeredis.FakeRedis(server=shared_server, decode_responses=True)
    RATE_LIMITER.set_redis_client(worker_one)
    _prepare_pending("192.0.2.20")
    assert FEEDBACK_STORE.label_as_bot("192.0.2.20") is True

    RATE_LIMITER.set_redis_client(worker_two)

    assert FEEDBACK_STORE.feedback_counts() == {
        "pending": 0,
        "human": 0,
        "bot": 1,
        "dropped": 0,
    }
