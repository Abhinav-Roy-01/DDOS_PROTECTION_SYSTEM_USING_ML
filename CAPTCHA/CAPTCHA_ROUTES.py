"""Short-lived, game-style challenge routes for suspicious demo traffic."""

import json
import logging
import os
import secrets
import time

from flask import Blueprint, jsonify, make_response, render_template, request
from redis.exceptions import RedisError

import PASS_TOKEN
import RATE_LIMITER
from FEEDBACK_STORE import (
    CHALLENGE_PREFIX,
    FeedbackConfigurationError,
    MAX_SOLVE_SECONDS,
    label_as_human,
)

captcha_bp = Blueprint(
    "captcha",
    __name__,
    template_folder="TEMPLATES",
    static_folder="STATIC",
    static_url_path="/static/captcha",
)
logger = logging.getLogger(__name__)
CHALLENGE_KEY_PREFIX = "SHIELD:CAPTCHA:CHALLENGE:"
CHALLENGE_TTL_SECONDS = 180
MAX_ATTEMPTS = 3
SEQUENCE_LENGTH = 3
SYMBOLS = ("circle", "square", "triangle", "star")


def _now():
    """Return epoch seconds through a patchable clock for tests."""
    return time.time()


def _client_ip():
    """Return the client IP determined by the trusted proxy configuration."""
    return request.remote_addr or ""


def _challenge_key(ip, challenge_id):
    """Build the IP-bound key for one short-lived game."""
    return f"{CHALLENGE_KEY_PREFIX}{ip}:{challenge_id}"


def _count(metric):
    """Increment a best-effort product counter."""
    RATE_LIMITER.increment_counter(metric)


@captcha_bp.get("/captcha/new_game")
def new_game():
    """Create one short-lived shape-sequence game for a challenged IP."""
    ip = _client_ip()
    redis_client = RATE_LIMITER.get_redis_client()
    try:
        if not redis_client.exists(CHALLENGE_PREFIX + ip):
            return jsonify({"status": "verification_required"}), 403
        challenge_id = secrets.token_urlsafe(24)
        sequence = secrets.SystemRandom().sample(SYMBOLS, SEQUENCE_LENGTH)
        choices = list(SYMBOLS)
        secrets.SystemRandom().shuffle(choices)
        state = {
            "sequence": sequence,
            "choices": choices,
            "issued_at": _now(),
            "attempts": 0,
        }
        redis_client.set(
            _challenge_key(ip, challenge_id),
            json.dumps(state, separators=(",", ":"), sort_keys=True),
            ex=CHALLENGE_TTL_SECONDS,
        )
    except RedisError as error:
        logger.error("Could not create CAPTCHA challenge: %s", error)
        return jsonify({"status": "service_unavailable"}), 503

    challenge = {"challenge_id": challenge_id, **state}
    if request.accept_mimetypes.best == "application/json":
        return jsonify(challenge)
    return render_template("captcha.html", challenge=challenge)


@captcha_bp.post("/captcha/verify")
def verify():
    """Validate a game sequence, label the pending sample, and issue a pass."""
    if request.mimetype != "application/json":
        return jsonify({"status": "invalid_request", "message": "Use application/json."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "invalid_request", "message": "Body must be a JSON object."}), 400
    challenge_id = payload.get("challenge_id")
    answers = payload.get("answers")
    if (
        not isinstance(challenge_id, str)
        or not 20 <= len(challenge_id) <= 64
        or not isinstance(answers, list)
        or len(answers) != SEQUENCE_LENGTH
        or any(not isinstance(answer, str) or answer not in SYMBOLS for answer in answers)
    ):
        return jsonify({"status": "invalid_request", "message": "Challenge answer is invalid."}), 400

    ip = _client_ip()
    redis_client = RATE_LIMITER.get_redis_client()
    key = _challenge_key(ip, challenge_id)
    try:
        raw_state = redis_client.get(key)
        if raw_state is None:
            _count("captcha_failed")
            return jsonify({"status": "challenge_expired"}), 403
        state = json.loads(raw_state)
        if not isinstance(state, dict) or not isinstance(state.get("sequence"), list):
            redis_client.delete(key)
            _count("captcha_failed")
            return jsonify({"status": "challenge_expired"}), 403

        elapsed = _now() - float(state["issued_at"])
        if elapsed < 3:
            return jsonify({
                "status": "try_again",
                "message": "Take a moment to complete the challenge.",
            }), 400
        if elapsed > MAX_SOLVE_SECONDS:
            redis_client.delete(key)
            _count("captcha_failed")
            return jsonify({"status": "challenge_expired"}), 403
        if answers != state["sequence"]:
            state["attempts"] += 1
            if state["attempts"] >= MAX_ATTEMPTS:
                redis_client.delete(key)
            else:
                redis_client.set(
                    key,
                    json.dumps(state, separators=(",", ":"), sort_keys=True),
                    ex=CHALLENGE_TTL_SECONDS,
                )
            _count("captcha_failed")
            return jsonify({"status": "incorrect"}), 403

        token = PASS_TOKEN.mint_pass_token(ip, verdict="captcha")
        if not label_as_human(ip, elapsed):
            redis_client.delete(key)
            _count("captcha_failed")
            return jsonify({"status": "verification_required"}), 403
        redis_client.delete(key, CHALLENGE_PREFIX + ip)
    except PASS_TOKEN.PassTokenConfigurationError as error:
        logger.error("Pass-token configuration is unavailable: %s", error)
        return jsonify({"status": "service_unavailable"}), 503
    except (FeedbackConfigurationError, RedisError, ValueError, TypeError) as error:
        logger.error("CAPTCHA verification is unavailable: %s", error)
        return jsonify({"status": "service_unavailable"}), 503

    _count("captcha_solved")
    response = make_response(jsonify({"status": "verified", "redirect": "/?captcha=solved"}))
    response.set_cookie(
        "ds_pass",
        token,
        max_age=PASS_TOKEN.TOKEN_LIFETIME_SECONDS,
        httponly=True,
        secure=os.environ.get("ENVIRONMENT", "development") == "production",
        samesite="Strict",
        path="/contact",
    )
    return response
