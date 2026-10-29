"""Tests for IP-bound, single-use pass tokens."""

import os
import sys

import fakeredis
import pytest
import redis

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from API import PASS_TOKEN


@pytest.fixture(autouse=True)
def configure_pass_token_secret(monkeypatch):
    """Set a test-only signing secret without reading the local .env file."""
    monkeypatch.setenv("PASS_TOKEN_SECRET", "test-secret-value-" + ("x" * 32))


@pytest.fixture
def redis_client():
    """Return an isolated Redis-compatible test client."""
    return fakeredis.FakeRedis(decode_responses=True)


def test_token_is_bound_to_ip_and_consumed_once(redis_client):
    """A valid token passes once for its original IP and cannot be replayed."""
    token = PASS_TOKEN.mint_pass_token("192.0.2.1", now=1000)

    assert PASS_TOKEN.verify_pass_token(token, "192.0.2.1", redis_client, now=1001) is True
    assert PASS_TOKEN.verify_pass_token(token, "192.0.2.1", redis_client, now=1002) is False


def test_token_rejects_another_ip(redis_client):
    """A correctly signed token cannot be used from another IP."""
    token = PASS_TOKEN.mint_pass_token("192.0.2.1", now=1000)

    assert PASS_TOKEN.verify_pass_token(token, "192.0.2.2", redis_client, now=1001) is False


def test_token_rejects_expired_and_future_issued_values(redis_client):
    """Tokens outside their signed time window are rejected."""
    expired = PASS_TOKEN.mint_pass_token("192.0.2.1", now=1000)
    future = PASS_TOKEN.mint_pass_token("192.0.2.1", now=2000)

    assert PASS_TOKEN.verify_pass_token(expired, "192.0.2.1", redis_client, now=1300) is False
    assert PASS_TOKEN.verify_pass_token(future, "192.0.2.1", redis_client, now=1999) is False


def test_token_rejects_tampering_and_logs_no_token(redis_client, caplog):
    """Tampered token contents are rejected without logging the token value."""
    token = PASS_TOKEN.mint_pass_token("192.0.2.1", now=1000)
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    assert PASS_TOKEN.verify_pass_token(tampered, "192.0.2.1", redis_client, now=1001) is False
    assert token not in caplog.text


def test_missing_or_short_secret_is_an_explicit_configuration_error(monkeypatch):
    """Token operations fail explicitly when no adequate secret is configured."""
    monkeypatch.setenv("PASS_TOKEN_SECRET", "")

    with pytest.raises(PASS_TOKEN.PassTokenConfigurationError):
        PASS_TOKEN.mint_pass_token("192.0.2.1")


def test_invalid_verdict_is_rejected_before_signing():
    """Only allow and CAPTCHA outcomes may mint a protected-action token."""
    with pytest.raises(ValueError):
        PASS_TOKEN.mint_pass_token("192.0.2.1", verdict="blocked")


def test_redis_outage_fails_closed():
    """A nonce store outage propagates instead of accepting an untracked token."""
    class BrokenRedis:
        """Raise the standard Redis connection error for every operation."""

        def set(self, *_args, **_kwargs):
            """Simulate a failed Redis SET operation."""
            _ = _args, _kwargs
            raise redis.exceptions.ConnectionError("redis is down")

    token = PASS_TOKEN.mint_pass_token("192.0.2.1", now=1000)

    with pytest.raises(redis.exceptions.ConnectionError):
        PASS_TOKEN.verify_pass_token(token, "192.0.2.1", BrokenRedis(), now=1001)
