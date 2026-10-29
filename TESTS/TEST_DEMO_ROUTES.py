"""Tests for the scoring and protected-contact demo routes."""

import os
import sys

import fakeredis
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "API"))

import SERVER

SERVER.add_project_paths()
import CAPTCHA_ROUTES
import DEMO_ROUTES
import RATE_LIMITER as RL

FEATURES = {
    "click_count": 8,
    "avg_click_interval": 900.0,
    "click_interval_variance": 200.0,
    "click_interval_entropy": 1.5,
    "mouse_velocity_variance": 0.3,
    "max_element_click_rate": 1.2,
    "scroll_events": 2,
    "keystroke_count": 14,
}
CONTACT = {
    "name": "Demo User",
    "email": "demo@example.test",
    "message": "Please contact me about the prototype.",
    "website": "",
}


class FakeEngine:
    def __init__(self):
        self.verdict = "allowed"
        self.score = 0.1

    def predict(self, features):
        return {
            "verdict": self.verdict,
            "score": self.score,
            "model_version": "test-version",
        }


@pytest.fixture
def demo_app(monkeypatch):
    monkeypatch.setenv("PASS_TOKEN_SECRET", "pass-token-test-secret-value-32-extra")
    monkeypatch.setenv("FEEDBACK_HASH_KEY", "feedback-hash-test-secret-value-32")
    monkeypatch.setenv("ENVIRONMENT", "development")
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    RL.set_redis_client(redis_client)
    engine = FakeEngine()
    monkeypatch.setattr(DEMO_ROUTES, "_engine", engine)
    app = SERVER.create_app()
    app.testing = True
    with app.test_client() as client:
        yield app, client, engine, redis_client
    RL.set_redis_client(None)
    monkeypatch.setattr(DEMO_ROUTES, "_engine", None)


def test_homepage_serves_the_protected_contact_form(demo_app):
    _, client, _, _ = demo_app
    response = client.get("/")

    assert response.status_code == 200
    assert b"Send a message" in response.data
    assert b"tracker.js" in response.data


def test_allowed_prediction_records_features_and_issues_cookie(demo_app):
    _, client, _, redis_client = demo_app
    response = client.post("/predict", json={"features": FEATURES}, environ_base={"REMOTE_ADDR": "203.0.113.1"})

    assert response.status_code == 200
    assert response.json == {"status": "allowed"}
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "Path=/contact" in cookie
    assert redis_client.get("SHIELD:PENDING:203.0.113.1") is not None
    assert RL.get_click_feed()[0]["verdict"] == "allowed"
    assert RL.get_counters()["predict_allowed"] == 1


def test_invalid_features_are_rejected_before_feedback_storage(demo_app):
    _, client, _, redis_client = demo_app
    response = client.post("/predict", json={"features": {"click_count": 2}})

    assert response.status_code == 400
    assert response.json["status"] == "invalid_request"
    assert redis_client.keys("SHIELD:PENDING:*") == []


def test_captcha_verdict_sets_challenge_state_without_pass_cookie(demo_app):
    _, client, engine, redis_client = demo_app
    engine.verdict = "captcha"

    response = client.post("/predict", json={"features": FEATURES}, environ_base={"REMOTE_ADDR": "203.0.113.2"})

    assert response.status_code == 403
    assert response.json == {"status": "captcha_required", "redirect": "/captcha/new_game"}
    assert response.headers.get("Set-Cookie") is None
    assert redis_client.get("captcha:required:203.0.113.2") == "1"
    assert RL.get_counters()["captcha_issued"] == 1


def test_block_verdict_bans_and_labels_the_pending_vector(demo_app):
    _, client, engine, redis_client = demo_app
    engine.verdict = "blocked"
    engine.score = -0.2

    response = client.post("/predict", json={"features": FEATURES}, environ_base={"REMOTE_ADDR": "203.0.113.3"})

    assert response.status_code == 403
    assert response.json == {"status": "blocked"}
    assert RL.is_banned("203.0.113.3")
    assert redis_client.llen("SHIELD:FEEDBACK:BOT") == 1


def test_predict_budget_returns_retry_after_after_twelve_calls(demo_app):
    _, client, _, _ = demo_app
    for _ in range(RL.PREDICT_LIMIT):
        assert client.post("/predict", json={"features": FEATURES}).status_code == 200

    response = client.post("/predict", json={"features": FEATURES})

    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(RL.PREDICT_WINDOW)


def test_contact_consumes_pass_token_and_stores_no_ip(demo_app):
    _, client, _, _ = demo_app
    scored = client.post("/predict", json={"features": FEATURES}, environ_base={"REMOTE_ADDR": "203.0.113.4"})
    assert scored.status_code == 200

    response = client.post("/contact", json=CONTACT, environ_base={"REMOTE_ADDR": "203.0.113.4"})

    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    message = RL.get_messages()[0]
    assert message["name"] == CONTACT["name"]
    assert message["email"] == CONTACT["email"]
    assert "ip" not in message
    assert "token" not in message
    assert RL.get_counters()["contact_ok"] == 1


def test_contact_rejects_replayed_pass_token(demo_app):
    _, client, _, _ = demo_app
    client.post("/predict", json={"features": FEATURES})
    token_cookie = client.get_cookie("ds_pass", path="/contact")
    assert token_cookie is not None
    assert client.post("/contact", json=CONTACT).status_code == 200

    response = client.post(
        "/contact",
        json=CONTACT,
        headers={"Cookie": f"ds_pass={token_cookie.value}"},
    )

    assert response.status_code == 403
    assert response.json["status"] == "verification_required"
    assert len(RL.get_messages()) == 1


def test_contact_rejects_honeypot_before_storing_message(demo_app):
    _, client, _, _ = demo_app
    client.post("/predict", json={"features": FEATURES})
    payload = {**CONTACT, "website": "filled"}

    response = client.post("/contact", json=payload)

    assert response.status_code == 403
    assert response.json["status"] == "verification_required"
    assert RL.get_messages() == []


def test_contact_requires_exact_json_content_type(demo_app):
    _, client, _, _ = demo_app

    response = client.post("/contact", data='{"name":"Demo"}', content_type="text/plain")

    assert response.status_code == 400
    assert response.json["status"] == "invalid_request"


def test_contact_requires_valid_pass_token(demo_app):
    _, client, _, _ = demo_app

    response = client.post("/contact", json=CONTACT)

    assert response.status_code == 403
    assert response.json["status"] == "verification_required"
    assert RL.get_messages() == []


def test_captcha_game_labels_human_and_issues_contact_pass(demo_app, monkeypatch):
    _, client, engine, redis_client = demo_app
    engine.verdict = "captcha"
    clock = {"now": 1_000.0}
    monkeypatch.setattr(CAPTCHA_ROUTES, "_now", lambda: clock["now"])
    ip = "203.0.113.5"
    assert client.post(
        "/predict",
        json={"features": FEATURES},
        environ_base={"REMOTE_ADDR": ip},
    ).status_code == 403

    game = client.get(
        "/captcha/new_game",
        headers={"Accept": "application/json"},
        environ_base={"REMOTE_ADDR": ip},
    )
    assert game.status_code == 200
    challenge = game.json
    assert len(set(challenge["sequence"])) == CAPTCHA_ROUTES.SEQUENCE_LENGTH
    clock["now"] += 4
    response = client.post(
        "/captcha/verify",
        json={
            "challenge_id": challenge["challenge_id"],
            "answers": challenge["sequence"],
        },
        environ_base={"REMOTE_ADDR": ip},
    )

    assert response.status_code == 200
    assert response.json["status"] == "verified"
    assert "Path=/contact" in response.headers["Set-Cookie"]
    assert redis_client.llen("SHIELD:FEEDBACK:HUMAN") == 1
    assert redis_client.get(f"captcha:required:{ip}") is None
    assert RL.get_counters()["captcha_solved"] == 1


def test_captcha_rejects_an_incorrect_sequence(demo_app, monkeypatch):
    _, client, engine, _ = demo_app
    engine.verdict = "captcha"
    clock = {"now": 1_000.0}
    monkeypatch.setattr(CAPTCHA_ROUTES, "_now", lambda: clock["now"])
    ip = "203.0.113.6"
    client.post(
        "/predict",
        json={"features": FEATURES},
        environ_base={"REMOTE_ADDR": ip},
    )
    challenge = client.get(
        "/captcha/new_game",
        headers={"Accept": "application/json"},
        environ_base={"REMOTE_ADDR": ip},
    ).json
    wrong_answers = [
        next(shape for shape in CAPTCHA_ROUTES.SYMBOLS if shape != challenge["sequence"][0]),
        *challenge["sequence"][1:],
    ]
    clock["now"] += 4

    response = client.post(
        "/captcha/verify",
        json={
            "challenge_id": challenge["challenge_id"],
            "answers": wrong_answers,
        },
        environ_base={"REMOTE_ADDR": ip},
    )

    assert response.status_code == 403
    assert response.json["status"] == "incorrect"
