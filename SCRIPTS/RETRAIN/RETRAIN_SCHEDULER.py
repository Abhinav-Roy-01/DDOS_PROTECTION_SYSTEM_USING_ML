"""Trigger the protected retraining API once or on a local schedule."""

import argparse
import math
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_API_URL = "http://127.0.0.1:8080"
REQUEST_TIMEOUT_SECONDS = 300


def _validate_url(api_url):
    """Require TLS for remote URLs so the admin key is not sent in plaintext."""
    parsed = urllib.parse.urlparse(api_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("API URL must be an absolute HTTP or HTTPS URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote retraining API URLs must use HTTPS.")
    return api_url.rstrip("/")


def trigger_retrain(api_url, admin_key, dry_run=False):
    """POST one authenticated, synchronous retraining request."""
    if not admin_key:
        raise ValueError("ADMIN_API_KEY must be configured.")
    url = _validate_url(api_url) + "/api/retrain/start"
    payload = json.dumps({"dry_run": dry_run}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Key": admin_key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Retraining API returned HTTP {error.code}: {details}") from error
    return result


def main():
    """Run one quality-gated retrain or repeat at the configured interval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default=os.environ.get("RETRAIN_API_URL", DEFAULT_API_URL))
    parser.add_argument("--interval-hours", type=float, default=24.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    _validate_url(args.api_url)
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    if not admin_key:
        parser.error("Set ADMIN_API_KEY before running the scheduler.")
    if not args.once and (
        not math.isfinite(args.interval_hours) or args.interval_hours <= 0
    ):
        parser.error("--interval-hours must be positive.")

    while True:
        result = trigger_retrain(args.api_url, admin_key, dry_run=args.dry_run)
        print(json.dumps(result, sort_keys=True))
        if args.once:
            return
        time.sleep(args.interval_hours * 60 * 60)


if __name__ == "__main__":
    main()
