"""Scoring and protected-contact routes for the local demo application."""

import logging
import os
import re
from datetime import datetime, timezone

from flask import Blueprint, g, jsonify, make_response, render_template, request
from redis.exceptions import RedisError

import ML_ENGINE
import PASS_TOKEN
import RATE_LIMITER
from FEEDBACK_STORE import (
    CHALLENGE_PREFIX,
    FeedbackConfigurationError,
    label_as_bot,
    record_pending,
)

demo_bp = Blueprint(
    "demo",
    __name__,
    template_folder="TEMPLATES",
    static_folder="STATIC",
    static_url_path="/static/demo",
)
logger = logging.getLogger(__name__)
_engine = None
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTACT_FIELDS = {
    "name": 100,
    "email": 254,
    "message": 2000,
}


def _get_engine():
    """Create the model engine only when the first prediction is requested."""
    global _engine
    if _engine is None:
        _engine = ML_ENGINE.MLEngine()
    return _engine


def _client_ip():
    """Return the client IP determined by the trusted proxy configuration."""
    return request.remote_addr or ""


def _count(metric):
    """Increment a best-effort product counter."""
    RATE_LIMITER.increment_counter(metric)


def _verification_required():
    """Return the common response for missing, expired, or replayed passes."""
    return jsonify({
        "status": "verification_required",
        "message": "Complete the verification before sending this request.",
    }), 403


@demo_bp.get("/")
def home():
    """Render the public protected-contact demonstration."""
    return render_template("index.html")


@demo_bp.post("/predict")
def predict():
    """Score one validated browser feature vector and route its verdict."""
    ip = _client_ip()
    if not RATE_LIMITER.check_predict_budget(ip):
        response = jsonify({
            "status": "rate_limited",
            "message": "Prediction budget exceeded.",
        })
        response.status_code = 429
        response.headers["Retry-After"] = str(RATE_LIMITER.PREDICT_WINDOW)
        return response

    if request.mimetype != "application/json":
        return jsonify({"status": "invalid_request", "message": "Use application/json."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "invalid_request", "message": "Body must be a JSON object."}), 400
    features = payload.get("features", payload)
    try:
        validated = ML_ENGINE.validate_features(features)
    except ML_ENGINE.FeatureValidationError as error:
        return jsonify({"status": "invalid_request", "message": str(error)}), 400

    try:
        record_pending(ip, validated)
    except (FeedbackConfigurationError, RedisError) as error:
        logger.warning("Could not save pending feedback: %s", error)

    try:
        result = _get_engine().predict(validated)
    except ML_ENGINE.FeatureValidationError as error:
        return jsonify({"status": "invalid_request", "message": str(error)}), 400
    except ML_ENGINE.ModelUnavailableError as error:
        logger.error("Prediction unavailable: %s", error)
        return jsonify({"status": "service_unavailable", "message": "Model is unavailable."}), 503

    verdict = result["verdict"]
    score = result["score"]
    g.ml_verdict = verdict
    g.ml_score = score
    RATE_LIMITER.record_score(score)
    RATE_LIMITER.record_click({
        **validated,
        "ip": ip,
        "verdict": verdict,
        "score": score,
    })

    if verdict == "allowed":
        _count("predict_allowed")
        try:
            token = PASS_TOKEN.mint_pass_token(ip, verdict="allowed")
        except PASS_TOKEN.PassTokenConfigurationError as error:
            logger.error("Pass-token configuration is unavailable: %s", error)
            return jsonify({
                "status": "service_unavailable",
                "message": "Protected actions are not configured.",
            }), 503
        response = make_response(jsonify({"status": "allowed"}))
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

    if verdict == "captcha":
        _count("predict_captcha")
        _count("captcha_issued")
        try:
            RATE_LIMITER.get_redis_client().set(
                CHALLENGE_PREFIX + ip,
                "1",
                ex=PASS_TOKEN.TOKEN_LIFETIME_SECONDS,
            )
        except RedisError as error:
            logger.warning("Could not record CAPTCHA requirement: %s", error)
        response = jsonify({
            "status": "captcha_required",
            "redirect": "/captcha/new_game",
        })
        response.status_code = 403
        return response

    _count("predict_blocked")
    g.blocked = True
    if not RATE_LIMITER.is_admin_ip_allowlisted(ip):
        RATE_LIMITER.manual_ban(ip)
    try:
        label_as_bot(ip)
    except (FeedbackConfigurationError, RedisError) as error:
        logger.warning("Could not label blocked prediction: %s", error)
    return jsonify({"status": "blocked"}), 403


@demo_bp.get("/contact")
def contact_form():
    """Render the protected contact form."""
    return render_template("index.html")


@demo_bp.post("/contact")
def contact():
    """Consume an IP-bound pass token and store one validated message."""
    if request.mimetype != "application/json":
        _count("contact_rejected")
        return jsonify({"status": "invalid_request", "message": "Use application/json."}), 400
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        _count("contact_rejected")
        return jsonify({"status": "invalid_request", "message": "Body must be a JSON object."}), 400

    values = {}
    for field, max_length in CONTACT_FIELDS.items():
        value = payload.get(field)
        if not isinstance(value, str):
            _count("contact_rejected")
            return jsonify({"status": "invalid_request", "message": f"'{field}' is required."}), 400
        value = value.strip()
        if not value or len(value) > max_length:
            _count("contact_rejected")
            return jsonify({"status": "invalid_request", "message": f"'{field}' is invalid."}), 400
        values[field] = value
    if not EMAIL_PATTERN.fullmatch(values["email"]):
        _count("contact_rejected")
        return jsonify({"status": "invalid_request", "message": "'email' is invalid."}), 400

    honeypot = payload.get("website", "")
    if not isinstance(honeypot, str):
        _count("contact_rejected")
        return _verification_required()
    if honeypot.strip():
        _count("contact_rejected")
        return _verification_required()

    ip = _client_ip()
    token = request.cookies.get("ds_pass", "")
    try:
        valid = PASS_TOKEN.verify_pass_token(
            token,
            ip,
            RATE_LIMITER.get_redis_client(),
        )
    except (PASS_TOKEN.PassTokenConfigurationError, RedisError) as error:
        logger.error("Contact verification is unavailable: %s", error)
        return jsonify({
            "status": "service_unavailable",
            "message": "Verification is temporarily unavailable.",
        }), 503
    if not valid:
        _count("contact_rejected")
        return _verification_required()

    message = {
        **values,
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        RATE_LIMITER.store_message(message)
    except RedisError as error:
        logger.error("Could not store verified contact message: %s", error)
        return jsonify({
            "status": "service_unavailable",
            "message": "The message could not be stored. Please try again.",
        }), 503

    _count("contact_ok")
    response = make_response(jsonify({"status": "ok"}))
    response.delete_cookie(
        "ds_pass",
        path="/contact",
        secure=os.environ.get("ENVIRONMENT", "development") == "production",
        httponly=True,
        samesite="Strict",
    )
    return response
