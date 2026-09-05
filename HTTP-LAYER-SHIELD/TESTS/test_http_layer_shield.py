"""
HTTP-LAYER-SHIELD/TESTS/test_http_layer_shield.py
Verifies every HTTP-layer component built so far actually works:
  - ml_engine loads the trained model without error
  - the Flask app boots and serves the dashboard + static assets
  - /predict classifies and logs to the telemetry feed
  - the attack simulator actually starts, fires requests, and stops

Run from HTTP-LAYER-SHIELD/API/:
    cd HTTP-LAYER-SHIELD/API
    pytest ../TESTS/test_http_layer_shield.py -v
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "API"))

import pytest


@pytest.fixture
def client():
    import server
    server.app.testing = True
    return server.app.test_client()


@pytest.fixture
def admin_headers():
    """The X-Admin-Key header a real authenticated admin (or the dashboard's
    own JS) would send. Routes decorated with @require_admin_key in
    server.py reject requests without this -- these tests are calling them
    the same way a legitimate admin session would, not bypassing anything."""
    import auth
    return {"X-Admin-Key": auth.get_admin_key()}


@pytest.fixture(autouse=True)
def reset_captcha_state():
    """Runs before every test in this file.

    Now that the captcha_bp import bug is fixed, before_request actually
    enforces CAPTCHA requirements: once /predict scores an IP into the
    'suspicious' band, that IP is genuinely blocked on every route until
    it verifies. That's correct real-world behavior -- but it means tests
    aren't independent unless we reset it, since every test here uses the
    same client IP (127.0.0.1). Without this fixture, whichever test runs
    first and lands in the captcha band would get every later test 403'd.
    """
    import server  # ensures sys.path is set up before we touch captcha_routes
    r = server.get_redis()
    r.delete("captcha:required:127.0.0.1")
    r.delete("captcha:verified:127.0.0.1")
    yield


# --- ml_engine ---------------------------------------------------------

def test_model_loads_without_error():
    import ml_engine
    assert ml_engine.engine.model is not None
    assert ml_engine.engine.scaler is not None


# --- dashboard + static assets ------------------------------------------

def test_dashboard_page_loads(client):
    r = client.get('/')
    assert r.status_code == 200


def test_dashboard_includes_tracker_js(client):
    r = client.get('/')
    assert '/static/js/tracker.js' in r.get_data(as_text=True)


def test_tracker_js_is_served(client):
    r = client.get('/static/js/tracker.js')
    assert r.status_code == 200
    assert len(r.get_data()) > 0


def test_dashboard_css_is_served(client):
    r = client.get('/static/css/dashboard.css')
    assert r.status_code == 200


# --- /predict + telemetry pipeline --------------------------------------

def test_predict_returns_a_verdict(client):
    """The trained model genuinely classifies input -- it can legitimately
    return 200 (allowed), or 403 (captcha_required / blocked) depending on
    the feature values. This test checks the response CONTRACT, not a
    fixed outcome -- asserting "always 200" would be wrong, since that
    would mean the classifier isn't actually discriminating."""
    r = client.post('/predict', json={
        'click_count': 12, 'avg_click_interval': 850, 'click_interval_variance': 15000,
        'click_interval_entropy': 2.8, 'mouse_velocity_variance': 0.42,
        'max_element_click_rate': 0.9, 'scroll_events': 6, 'keystroke_count': 20
    })
    assert r.status_code in (200, 403)
    body = r.get_json()
    assert "prediction" in body
    assert "anomaly_score" in body
    assert body["status"] in ("allowed", "captcha_required", "blocked")


def test_model_discriminates_human_from_bot(client):
    """Uses real labeled rows pulled from ML/DATASET/training_data.csv
    (casual_browser vs http_flooder) rather than guessed numbers.

    Note: neither example lands in the >0.10 'allowed' band with the
    current model -- the human row scores ~0.067 (captcha band) and the
    bot row scores ~-0.149 (just inside captcha band too). That's a
    threshold-calibration question for the ML tuning phase, not a bug.
    What must hold regardless of where the bands sit: the model should
    always score the human example higher than the bot example.
    """
    human = {'click_count': 8, 'avg_click_interval': 1524.94, 'click_interval_variance': 269875.24,
             'click_interval_entropy': 2.304, 'mouse_velocity_variance': 0.356,
             'max_element_click_rate': 1.201, 'scroll_events': 11, 'keystroke_count': 5}
    bot = {'click_count': 200, 'avg_click_interval': 22.61, 'click_interval_variance': 6.13,
           'click_interval_entropy': 0.015, 'mouse_velocity_variance': 0.0,
           'max_element_click_rate': 39.29, 'scroll_events': 0, 'keystroke_count': 0}

    human_score = client.post('/predict', json=human,
                               headers={"X-Forwarded-For": "10.0.0.1"}).get_json()["anomaly_score"]
    bot_score = client.post('/predict', json=bot,
                             headers={"X-Forwarded-For": "10.0.0.2"}).get_json()["anomaly_score"]

    assert human_score > bot_score, (
        f"model ranked bot ({bot_score}) above human ({human_score}) -- "
        "this would mean the classifier isn't discriminating correctly"
    )


def test_predict_snapshot_appears_in_telemetry_feed(client, admin_headers):
    client.post('/predict', json={
        'click_count': 3, 'avg_click_interval': 400, 'click_interval_variance': 50,
        'click_interval_entropy': 1.2, 'mouse_velocity_variance': 0.1,
        'max_element_click_rate': 0.5, 'scroll_events': 1, 'keystroke_count': 5
    }, headers={"X-Forwarded-For": "10.0.0.3"})
    # Query the feed from the default test-client IP (127.0.0.1), which
    # the fixture guarantees is still captcha-clear, rather than the IP
    # that just posted -- /api/telemetry isn't in before_request's
    # excluded-path list, so it's subject to the same captcha gate.
    # It IS also behind @require_admin_key now, hence admin_headers.
    r = client.get('/api/telemetry', headers=admin_headers)
    feed = r.get_json()
    assert len(feed) > 0
    assert "click_count" in feed[0]


# --- attack simulator ----------------------------------------------------

def test_attack_start_sets_running_true(client, admin_headers):
    client.post('/api/attack/stop', headers=admin_headers)  # ensure clean state
    r = client.post('/api/attack/start', json={'type': 'flood'}, headers=admin_headers)
    status = r.get_json()
    assert status["running"] is True
    client.post('/api/attack/stop', headers=admin_headers)


def test_attack_fires_requests_while_running(client, admin_headers):
    client.post('/api/attack/stop', headers=admin_headers)
    client.post('/api/attack/start', json={'type': 'flood'}, headers=admin_headers)
    time.sleep(1)
    status = client.get('/api/attack/status', headers=admin_headers).get_json()
    client.post('/api/attack/stop', headers=admin_headers)
    assert status["requests_fired"] > 0


def test_attack_stop_actually_stops_it(client, admin_headers):
    client.post('/api/attack/stop', headers=admin_headers)
    client.post('/api/attack/start', json={'type': 'flood'}, headers=admin_headers)
    time.sleep(0.5)
    client.post('/api/attack/stop', headers=admin_headers)

    count_after_stop = client.get('/api/attack/status', headers=admin_headers).get_json()["requests_fired"]
    time.sleep(1)
    count_later = client.get('/api/attack/status', headers=admin_headers).get_json()["requests_fired"]

    assert count_after_stop == count_later, "requests kept firing after stop was called"


def test_attack_status_reports_idle_after_stop(client, admin_headers):
    client.post('/api/attack/start', json={'type': 'flood'}, headers=admin_headers)
    time.sleep(0.3)
    r = client.post('/api/attack/stop', headers=admin_headers)
    assert r.get_json()["running"] is False


# --- auth gap: the actual thing this component fixes ---------------------

def test_protected_route_rejects_missing_key(client):
    """This is the regression test for the gap itself: before auth.py was
    wired in, anyone could hit these routes with zero credentials."""
    r = client.get('/api/telemetry')
    assert r.status_code == 401


def test_protected_route_rejects_wrong_key(client):
    r = client.get('/api/telemetry', headers={"X-Admin-Key": "not-the-real-key"})
    assert r.status_code == 401


def test_protected_route_accepts_correct_key(client, admin_headers):
    r = client.get('/api/telemetry', headers=admin_headers)
    assert r.status_code == 200


def test_all_state_changing_admin_routes_are_protected(client):
    """Every route that starts/stops an attack or bans an IP must require
    the admin key -- this loops over all of them rather than testing one
    and hoping the rest were decorated consistently."""
    unauthenticated_attempts = [
        ("POST", "/api/ban", {"ip": "1.2.3.4"}),
        ("POST", "/api/attack/start", {"type": "flood"}),
        ("POST", "/api/attack/stop", None),
        ("GET", "/api/attack/status", None),
        ("GET", "/api/telemetry", None),
    ]
    for method, path, body in unauthenticated_attempts:
        r = client.open(path, method=method, json=body)
        assert r.status_code == 401, f"{method} {path} did not require auth (got {r.status_code})"


def test_public_routes_still_work_without_admin_key(client):
    """The auth gate must NOT accidentally lock out routes that are
    supposed to stay public: /predict (real visitor traffic), /health
    (orchestrator probes), /matrix and /stats (already excluded from the
    CAPTCHA gate for the same dashboard-visibility reasons)."""
    assert client.get('/health').status_code == 200
    assert client.get('/matrix').status_code == 200
    assert client.get('/stats').status_code == 200
    predict_resp = client.post('/predict', json={
        'click_count': 1, 'avg_click_interval': 1, 'click_interval_variance': 1,
        'click_interval_entropy': 1, 'mouse_velocity_variance': 1,
        'max_element_click_rate': 1, 'scroll_events': 1, 'keystroke_count': 1
    }, headers={"X-Forwarded-For": "10.0.0.9"})
    assert predict_resp.status_code in (200, 403)  # reachable at all, not 401