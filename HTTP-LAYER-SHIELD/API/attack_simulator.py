"""
API/attack_simulator.py
Real-time attack simulator — runs in a background thread until you stop it.

Replaces the old one-shot /api/attack (which fired 70 requests once and
returned immediately — no "running" state, nothing to stop).

Two attack types:
  - "flood":      many requests per second from a small pool of fake IPs
                   (classic volumetric DDoS)
  - "slowloris":   fewer requests per second, but from many distinct fake
                   IPs (mimics a distributed low-and-slow botnet)

Wire-up (done for you in server.py):
  POST /api/attack/start   {"type": "flood" | "slowloris"}
  POST /api/attack/stop
  GET  /api/attack/status
"""

import threading
import time
import random

from rate_limiter import check_rate_limit, record_request, is_banned

_lock = threading.Lock()
_thread: threading.Thread | None = None
_stop_event = threading.Event()
_state = {
    "running": False,
    "type": None,
    "started_at": None,
    "requests_fired": 0,
}

# Fake attacker IP pools
_FLOOD_IPS = ["203.0.113.9"]                                   # one hammering IP
_SLOWLORIS_IPS = [f"198.51.100.{i}" for i in range(2, 40)]      # many distinct IPs


def _flood_loop():
    """One IP, as many requests as possible, fastest way to trip BAN_THRESHOLD."""
    ip = _FLOOD_IPS[0]
    while not _stop_event.is_set():
        check_rate_limit(ip)
        record_request(ip, "/api/resource", "GET", blocked=is_banned(ip))
        with _lock:
            _state["requests_fired"] += 1
        time.sleep(0.05)  # ~20 req/sec from this one IP


def _slowloris_loop():
    """Many IPs, low rate each, harder for simple per-IP rate limiting to catch."""
    while not _stop_event.is_set():
        ip = random.choice(_SLOWLORIS_IPS)
        check_rate_limit(ip)
        record_request(ip, "/api/resource", "GET", blocked=is_banned(ip))
        with _lock:
            _state["requests_fired"] += 1
        time.sleep(0.3)  # ~3 req/sec, spread across many IPs


def start_attack(attack_type: str = "flood"):
    global _thread
    with _lock:
        if _state["running"]:
            return get_status()  # already running, no-op
        _stop_event.clear()
        _state.update(running=True, type=attack_type, started_at=time.time(), requests_fired=0)

    target = _slowloris_loop if attack_type == "slowloris" else _flood_loop
    _thread = threading.Thread(target=target, daemon=True)
    _thread.start()
    return get_status()


def stop_attack():
    global _thread
    _stop_event.set()
    if _thread is not None:
        _thread.join(timeout=2)
    with _lock:
        _state["running"] = False
    return get_status()


def get_status():
    with _lock:
        s = dict(_state)
    if s["started_at"]:
        s["elapsed_sec"] = round(time.time() - s["started_at"], 1)
    else:
        s["elapsed_sec"] = 0
    return s
