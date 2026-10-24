"""
TEST_SERVER.PY -- tests for API/SERVER.py and API/AUTH.py.

Uses fakeredis, so no real Redis server is needed.
Run from the project root:
    pytest TESTS/TEST_SERVER.py -v
"""

import os
import sys

import fakeredis
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "API"))

import RATE_LIMITER as RL
import SERVER

ADMIN_KEY = "test-admin-key"
ADMIN_HEADERS = {"X-Admin-Key": ADMIN_KEY}


@pytest.fixture(autouse=True)
def fresh_redis():
    """Every test gets a brand-new empty fake Redis."""
    RL.set_redis_client(fakeredis.FakeRedis(decode_responses=True))
    yield
    RL.set_redis_client(None)


@pytest.fixture
def client(monkeypatch):
    """Test client with an admin key set and no trusted proxies."""
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")
    app = SERVER.create_app()
    app.testing = True
    return app.test_client()


# --- HEALTH -----------------------------------------------------------------

def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "OK"}


def test_health_is_never_rate_limited(client):
    for _ in range(RL.RATE_LIMIT + 20):
        assert client.get("/health").status_code == 200


# --- ADMIN KEY --------------------------------------------------------------

def test_admin_route_without_key_is_401(client):
    assert client.get("/api/stats").status_code == 401


def test_admin_route_with_wrong_key_is_401(client):
    response = client.get("/api/stats", headers={"X-Admin-Key": "wrong"})
    assert response.status_code == 401


def test_admin_route_with_correct_key_is_200(client):
    response = client.get("/api/stats", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert "total_requests" in response.get_json()


def test_admin_route_is_503_when_no_key_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "")
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")
    app = SERVER.create_app()
    app.testing = True
    response = app.test_client().get("/api/stats", headers=ADMIN_HEADERS)
    assert response.status_code == 503


def test_matrix_route_returns_timeline(client):
    response = client.get("/api/matrix", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert len(response.get_json()["timeline"]) == 60


# --- RATE LIMITING + BANS -----------------------------------------------------

def test_requests_over_the_limit_get_429(client):
    for _ in range(RL.RATE_LIMIT):
        assert client.get("/api/stats", headers=ADMIN_HEADERS).status_code == 200
    response = client.get("/api/stats", headers=ADMIN_HEADERS)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(RL.RATE_WINDOW)


def test_banned_ip_gets_403_and_health_still_works(client):
    RL.manual_ban("127.0.0.1")
    assert client.get("/api/stats", headers=ADMIN_HEADERS).status_code == 403
    assert client.get("/health").status_code == 200


def test_ban_and_unban_routes(client):
    ban = client.post("/api/ban", json={"ip": "9.9.9.9"}, headers=ADMIN_HEADERS)
    assert ban.status_code == 200
    assert RL.is_banned("9.9.9.9") is True

    unban = client.post("/api/unban", json={"ip": "9.9.9.9"}, headers=ADMIN_HEADERS)
    assert unban.get_json()["status"] == "unbanned"
    assert RL.is_banned("9.9.9.9") is False


def test_ban_route_rejects_invalid_ip(client):
    response = client.post("/api/ban", json={"ip": "not-an-ip"}, headers=ADMIN_HEADERS)
    assert response.status_code == 400


def test_blocked_requests_show_up_in_stats(client):
    RL.manual_ban("127.0.0.1")
    client.get("/api/stats", headers=ADMIN_HEADERS)          # blocked (403)
    RL.manual_unban("127.0.0.1")
    stats = client.get("/api/stats", headers=ADMIN_HEADERS).get_json()
    assert stats["blocked_requests"] >= 1


# --- PROXY HANDLING (real client IP behind nginx) ------------------------------

def test_forwarded_ip_is_ignored_when_no_proxy_is_trusted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "0")
    app = SERVER.create_app()
    app.testing = True
    RL.manual_ban("5.5.5.5")
    response = app.test_client().get(
        "/api/stats", headers={**ADMIN_HEADERS, "X-Forwarded-For": "5.5.5.5"})
    assert response.status_code == 200      # fake header did not change the IP


def test_forwarded_ip_is_used_when_one_proxy_is_trusted(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("TRUSTED_PROXY_COUNT", "1")
    app = SERVER.create_app()
    app.testing = True
    RL.manual_ban("5.5.5.5")
    response = app.test_client().get(
        "/api/stats", headers={**ADMIN_HEADERS, "X-Forwarded-For": "5.5.5.5"})
    assert response.status_code == 403      # real client IP was read and banned
