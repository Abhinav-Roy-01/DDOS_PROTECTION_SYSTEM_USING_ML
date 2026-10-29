"""Run quality-gated retraining against capped, verified Redis feedback."""

import json
import logging
import secrets
from datetime import datetime, timezone

import RATE_LIMITER
from FEEDBACK_STORE import abort_export, commit_export, export_for_training
from ML.TRAINING import RETRAIN

logger = logging.getLogger(__name__)
LOCK_KEY = "SHIELD:RETRAIN:LOCK"
STATUS_KEY = "SHIELD:RETRAIN:STATUS"
LOCK_TTL_SECONDS = 3600
MIN_FEEDBACK_PER_LABEL = 20


def _now():
    """Return a UTC timestamp for shared retraining status."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_status(client, status):
    """Persist a bounded JSON status record without training-row contents."""
    client.set(STATUS_KEY, json.dumps(status, sort_keys=True, separators=(",", ":")))


def _release_lock(client, token):
    """Release only this run's retraining lock."""
    if client.get(LOCK_KEY) == token:
        client.delete(LOCK_KEY)


def start_retrain(dry_run=False):
    """Export feedback, train synchronously, and commit only a passing bundle."""
    if not isinstance(dry_run, bool):
        raise ValueError("dry_run must be a boolean.")
    client = RATE_LIMITER.get_redis_client()
    token = secrets.token_urlsafe(24)
    if not client.set(LOCK_KEY, token, nx=True, ex=LOCK_TTL_SECONDS):
        return {"status": "running", "message": "A retraining run is already active."}, 409

    started_at = _now()
    exported = False
    status = {
        "status": "running",
        "started_at": started_at,
        "finished_at": None,
        "dry_run": dry_run,
    }
    _write_status(client, status)
    try:
        exported = True
        human_rows, bot_rows = export_for_training()
        result = RETRAIN.retrain(
            human_rows,
            bot_rows,
            min_feedback=MIN_FEEDBACK_PER_LABEL,
            dry_run=dry_run,
        )
        if dry_run:
            abort_export()
            exported = False
        else:
            commit_export()
            exported = False
            from DEMO_ROUTES import _get_engine

            engine = _get_engine()
            runtime_reload = engine.reload_model(force=True)
            if not runtime_reload:
                logger.error("A deployed bundle was not reloaded in the serving process.")
            result["runtime_reload"] = runtime_reload

        status = {
            "status": "dry_run_passed" if dry_run else "deployed",
            "started_at": started_at,
            "finished_at": _now(),
            "dry_run": dry_run,
            "result": result,
        }
        _write_status(client, status)
        return status, 200
    except RETRAIN.InsufficientFeedbackError as error:
        status = {
            "status": "rejected",
            "started_at": started_at,
            "finished_at": _now(),
            "dry_run": dry_run,
            "message": str(error),
        }
        _write_status(client, status)
        return status, 409
    except (RETRAIN.ModelQualityError, OSError, RuntimeError, ValueError) as error:
        logger.exception("Retraining run failed.")
        status = {
            "status": "failed",
            "started_at": started_at,
            "finished_at": _now(),
            "dry_run": dry_run,
            "message": str(error),
        }
        _write_status(client, status)
        return status, 422
    finally:
        if exported:
            abort_export()
        _release_lock(client, token)


def get_retrain_status():
    """Return the last shared retraining status or an idle state."""
    raw = RATE_LIMITER.get_redis_client().get(STATUS_KEY)
    return json.loads(raw) if raw is not None else {"status": "idle"}
