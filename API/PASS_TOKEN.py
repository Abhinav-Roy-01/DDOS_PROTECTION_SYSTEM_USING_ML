"""Issue and verify one-time, IP-bound tokens for the protected contact action."""

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time

TOKEN_LIFETIME_SECONDS = 300
NONCE_TTL_SECONDS = 600
MAX_TOKEN_LENGTH = 2048
NONCE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
USED_NONCE_KEY = "SHIELD:PASS:USED:"
logger = logging.getLogger(__name__)


class PassTokenConfigurationError(RuntimeError):
    """Raised when the signing secret is missing or too weak."""


def _secret_bytes():
    """Return the configured HMAC secret without a default value."""
    secret = os.environ.get("PASS_TOKEN_SECRET", "")
    encoded_secret = secret.encode("utf-8")
    if len(encoded_secret) < 32:
        raise PassTokenConfigurationError("PASS_TOKEN_SECRET must contain at least 32 bytes.")
    return encoded_secret


def _encode_segment(value):
    """Encode bytes as an unpadded URL-safe base64 token segment."""
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode_segment(value):
    """Decode one unpadded URL-safe base64 token segment."""
    padded = value + ("=" * (-len(value) % 4))
    return base64.b64decode(padded, altchars=b"-_", validate=True)


def _reject(reason):
    """Log a non-sensitive rejection reason and return False."""
    logger.info("pass_token_rejected reason=%s", reason)
    return False


def mint_pass_token(ip, verdict="allowed", now=None):
    """Sign a five-minute pass token bound to the client's IP and verdict."""
    if verdict not in {"allowed", "captcha"}:
        raise ValueError("Pass tokens require an allowed or CAPTCHA verdict.")
    issued_at = int(time.time() if now is None else now)
    payload = {
        "exp": issued_at + TOKEN_LIFETIME_SECONDS,
        "iat": issued_at,
        "ip": str(ip),
        "nonce": secrets.token_hex(16),
        "verdict": verdict,
    }
    encoded_payload = _encode_segment(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(_secret_bytes(), encoded_payload.encode("ascii"), hashlib.sha256)
    return f"{encoded_payload}.{_encode_segment(signature.digest())}"


def verify_pass_token(token, ip, redis_client, now=None):
    """Verify a pass token and atomically consume its nonce in Redis."""
    try:
        if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
            return _reject("format")
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
        supplied_signature = _decode_segment(encoded_signature)
        expected_signature = hmac.new(
            _secret_bytes(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
    except PassTokenConfigurationError:
        raise
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return _reject("format")

    if not hmac.compare_digest(supplied_signature, expected_signature):
        return _reject("signature")

    try:
        payload = json.loads(_decode_segment(encoded_payload))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return _reject("payload")

    if not isinstance(payload, dict):
        return _reject("payload")
    if payload.get("ip") != str(ip):
        return _reject("ip_mismatch")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    nonce = payload.get("nonce")
    if (
        isinstance(issued_at, bool)
        or not isinstance(issued_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(expires_at, int)
        or expires_at - issued_at != TOKEN_LIFETIME_SECONDS
    ):
        return _reject("time_fields")
    current_time = int(time.time() if now is None else now)
    if issued_at > current_time:
        return _reject("issued_in_future")
    if expires_at <= current_time:
        return _reject("expired")
    if not isinstance(nonce, str) or not NONCE_PATTERN.fullmatch(nonce):
        return _reject("nonce")
    if payload.get("verdict") not in {"allowed", "captcha"}:
        return _reject("verdict")

    consumed = redis_client.set(
        USED_NONCE_KEY + nonce,
        "1",
        nx=True,
        ex=NONCE_TTL_SECONDS,
    )
    if not consumed:
        return _reject("replay")
    return True
