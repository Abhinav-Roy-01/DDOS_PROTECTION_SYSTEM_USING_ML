"""Tests for the admin retraining lock, feedback lifecycle, and status."""

import os
import sys

import fakeredis
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, "API"))
sys.path.insert(0, os.path.join(ROOT_DIR, "FEEDBACK"))
sys.path.insert(0, os.path.join(ROOT_DIR, "SCRIPTS", "RETRAIN"))

import RATE_LIMITER as RL
import RETRAIN_RUNNER as RUNNER
import RETRAIN_SCHEDULER
from ML.TRAINING import RETRAIN


@pytest.fixture(autouse=True)
def fresh_redis():
    RL.set_redis_client(fakeredis.FakeRedis(decode_responses=True))
    yield
    RL.set_redis_client(None)


def test_dry_run_restores_feedback_and_persists_status(monkeypatch):
    calls = []
    monkeypatch.setattr(RUNNER, "export_for_training", lambda: ([], []))
    monkeypatch.setattr(RUNNER, "abort_export", lambda: calls.append("abort"))
    monkeypatch.setattr(
        RUNNER.RETRAIN,
        "retrain",
        lambda *args, **kwargs: {"deployed": False, "model_version": "candidate"},
    )

    result, status_code = RUNNER.start_retrain(dry_run=True)

    assert status_code == 200
    assert result["status"] == "dry_run_passed"
    assert calls == ["abort"]
    assert RUNNER.get_retrain_status()["result"]["model_version"] == "candidate"
    assert RL.get_redis_client().get(RUNNER.LOCK_KEY) is None


def test_insufficient_feedback_is_rejected_and_export_is_aborted(monkeypatch):
    calls = []
    monkeypatch.setattr(RUNNER, "export_for_training", lambda: ([], []))
    monkeypatch.setattr(RUNNER, "abort_export", lambda: calls.append("abort"))

    def reject(*_args, **_kwargs):
        raise RETRAIN.InsufficientFeedbackError("not enough verified feedback")

    monkeypatch.setattr(RUNNER.RETRAIN, "retrain", reject)
    result, status_code = RUNNER.start_retrain()

    assert status_code == 409
    assert result["status"] == "rejected"
    assert calls == ["abort"]


def test_concurrent_retrain_request_is_rejected():
    client = RL.get_redis_client()
    client.set(RUNNER.LOCK_KEY, "another-run", ex=RUNNER.LOCK_TTL_SECONDS)

    result, status_code = RUNNER.start_retrain()

    assert status_code == 409
    assert result["status"] == "running"


def test_training_failure_aborts_export_and_releases_lock(monkeypatch):
    calls = []
    monkeypatch.setattr(RUNNER, "export_for_training", lambda: ([], []))
    monkeypatch.setattr(RUNNER, "abort_export", lambda: calls.append("abort"))

    def fail(*_args, **_kwargs):
        raise OSError("candidate write failed")

    monkeypatch.setattr(RUNNER.RETRAIN, "retrain", fail)
    result, status_code = RUNNER.start_retrain()

    assert status_code == 422
    assert result["status"] == "failed"
    assert calls == ["abort"]
    assert RL.get_redis_client().get(RUNNER.LOCK_KEY) is None


def test_dry_run_argument_must_be_boolean():
    with pytest.raises(ValueError, match="dry_run"):
        RUNNER.start_retrain(dry_run="true")


def test_remote_retraining_urls_require_tls():
    with pytest.raises(ValueError, match="HTTPS"):
        RETRAIN_SCHEDULER._validate_url("http://admin.example.test")

    assert RETRAIN_SCHEDULER._validate_url("http://127.0.0.1:8080/") == "http://127.0.0.1:8080"
    assert RETRAIN_SCHEDULER._validate_url("https://admin.example.test") == "https://admin.example.test"
