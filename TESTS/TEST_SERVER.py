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

SERVER.add_project_paths()
import DEMO_ROUTES
import RETRAIN_RUNNER

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
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


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


def test_request_log_contains_request_id_and_status(client):
    response = client.get("/api/stats", headers=ADMIN_HEADERS)
    latest = RL.get_stats()["recent_requests"][-1]

    assert latest["request_id"] == response.headers["X-Request-ID"]
    assert latest["status_code"] == 200


def test_unknown_route_returns_json(client):
    response = client.get("/missing-route")

    assert response.status_code == 404
    assert response.get_json()["status"] == "not_found"


# --- RATE LIMITING + BANS -----------------------------------------------------

def test_requests_over_the_limit_get_429(client):
    for _ in range(RL.RATE_LIMIT):
        assert client.get("/api/stats", headers=ADMIN_HEADERS).status_code == 200
    response = client.get("/api/stats", headers=ADMIN_HEADERS)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == str(RL.RATE_WINDOW)


def test_banned_ip_gets_403_and_health_still_works(client):
    ip = "203.0.113.10"
    RL.manual_ban(ip)
    assert client.get("/", environ_base={"REMOTE_ADDR": ip}).status_code == 403
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
    ip = "203.0.113.11"
    RL.manual_ban(ip)
    client.get("/", environ_base={"REMOTE_ADDR": ip})        # blocked (403)
    RL.manual_unban(ip)
    stats = client.get("/api/stats", headers=ADMIN_HEADERS).get_json()
    assert stats["blocked_requests"] >= 1


def test_admin_routes_reject_non_allowlisted_sources(client):
    response = client.get(
        "/api/stats",
        headers=ADMIN_HEADERS,
        environ_base={"REMOTE_ADDR": "203.0.113.12"},
    )

    assert response.status_code == 403
    assert response.json["status"] == "admin_ip_not_allowed"


def test_admin_ban_route_refuses_allowlisted_addresses(client):
    response = client.post(
        "/api/ban",
        json={"ip": "127.0.0.1"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 409
    assert response.json["status"] == "refused"
    assert not RL.is_banned("127.0.0.1")


def test_admin_can_unban_a_normalized_ipv6_subnet(client):
    subnet = "2001:db8:abcd:1::/64"
    RL.manual_ban("2001:db8:abcd:1::1234")

    response = client.post(
        "/api/unban",
        json={"ip": subnet},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    assert response.json["status"] == "unbanned"
    assert not RL.is_banned("2001:db8:abcd:1::1")


def test_admin_bucket_is_separate_from_public_bucket(client):
    for _ in range(RL.RATE_LIMIT):
        RL.check_rate_limit("127.0.0.1")

    response = client.get("/api/stats", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert not RL.is_banned("127.0.0.1")


def test_dashboard_shell_and_admin_data_endpoints(client, monkeypatch):
    class DashboardEngine:
        def get_status(self):
            return {
                "degraded": False,
                "model_version": "test-version",
                "thresholds": {"block_below": -0.14, "captcha_below": -0.015},
            }

    monkeypatch.setattr(DEMO_ROUTES, "_engine", DashboardEngine())
    page = client.get("/dashboard")
    unauthorized = client.get("/api/overview")
    overview = client.get("/api/overview", headers=ADMIN_HEADERS)
    messages = client.get("/api/messages?limit=20", headers=ADMIN_HEADERS)

    assert page.status_code == 200
    assert b"Protection overview" in page.data
    assert unauthorized.status_code == 401
    assert overview.status_code == 200
    assert overview.json["model"]["model_version"] == "test-version"
    assert messages.status_code == 200
    assert messages.json == {"messages": []}


def test_dashboard_api_rejects_bad_message_limit(client):
    response = client.get("/api/messages?limit=1000", headers=ADMIN_HEADERS)

    assert response.status_code == 400
    assert response.json["status"] == "invalid_request"


def test_retraining_routes_are_admin_protected_and_validate_dry_run(client, monkeypatch):
    monkeypatch.setattr(
        RETRAIN_RUNNER,
        "start_retrain",
        lambda dry_run=False: ({"status": "dry_run_passed", "dry_run": dry_run}, 200),
    )
    unauthorized = client.get("/api/retrain/status")
    invalid = client.post(
        "/api/retrain/start",
        json={"dry_run": "yes"},
        headers=ADMIN_HEADERS,
    )
    started = client.post(
        "/api/retrain/start",
        json={"dry_run": True},
        headers=ADMIN_HEADERS,
    )

    assert unauthorized.status_code == 401
    assert invalid.status_code == 400
    assert started.status_code == 200
    assert started.json == {"status": "dry_run_passed", "dry_run": True}


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
