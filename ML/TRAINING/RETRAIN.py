"""Bootstrap a verified production-format IsolationForest model bundle."""

import argparse
import hashlib
import json
import os
import pickle
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

ROOT_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT_DIR / "ML" / "DATASET"
MODEL_DIR = ROOT_DIR / "ML" / "MODELS"
API_DIR = ROOT_DIR / "API"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from API.ML_ENGINE import (
    DEFAULT_THRESHOLDS,
    FEATURES,
    MLEngine,
    route_score,
    validate_features,
)

MODEL_PARAMS = {
    "n_estimators": 100,
    "contamination": 0.01,
    "random_state": 42,
    "n_jobs": 1,
}
QUALITY_GATE_MIN_ALLOWED_RATE = 95.0
QUALITY_GATE_MAX_BLOCKED_RATE = 0.0
BUNDLE_FILES = (
    "aethercept_model.pkl",
    "aethercept_scaler.pkl",
    "METADATA.json",
    "THRESHOLDS.json",
)


class InsufficientFeedbackError(ValueError):
    """Raised when a retraining run does not have enough verified examples."""


class ModelQualityError(ValueError):
    """Raised when a candidate model does not pass the human canary gate."""


def _sha256_file(path):
    """Return a file's SHA-256 digest."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path, data):
    """Write bytes to a temporary file and atomically replace the destination."""
    destination = Path(path)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file_handle:
            temporary_path = Path(file_handle.name)
            file_handle.write(data)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _git_commit():
    """Return the repository's current commit or 'unknown' outside a Git checkout."""
    result = subprocess.run(
        ["git", "-C", str(ROOT_DIR), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _read_base_data(dataset_dir):
    """Load and validate the synthetic training and human-only CSV files."""
    data_dir = Path(dataset_dir)
    human_path = data_dir / "human_only.csv"
    training_path = data_dir / "training_data.csv"
    humans = pd.read_csv(human_path)
    training = pd.read_csv(training_path)
    if humans.columns.tolist() != FEATURES:
        raise ValueError("human_only.csv columns do not match the feature contract.")
    if not set(FEATURES).issubset(training.columns):
        raise ValueError("training_data.csv is missing feature columns.")
    if "label" not in training.columns:
        raise ValueError("training_data.csv is missing the label column.")
    if not training["label"].isin(["human", "bot"]).all():
        raise ValueError("training_data.csv contains an unsupported label.")
    if humans.empty or not np.isfinite(humans[FEATURES].to_numpy(dtype=float)).all():
        raise ValueError("human_only.csv must contain finite numeric rows.")
    return humans[FEATURES], training


def _save_bundle(model, scaler, metadata, thresholds, model_dir):
    """Atomically save model artifacts and publish thresholds as the final signal."""
    output_dir = Path(model_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths = {
        "aethercept_model.pkl": output_dir / "aethercept_model.pkl",
        "aethercept_scaler.pkl": output_dir / "aethercept_scaler.pkl",
    }

    for name, value in (("aethercept_model.pkl", model), ("aethercept_scaler.pkl", scaler)):
        temporary_path = output_dir / f".{name}.tmp"
        with temporary_path.open("wb") as file_handle:
            pickle.dump(value, file_handle, protocol=pickle.HIGHEST_PROTOCOL)
            file_handle.flush()
            os.fsync(file_handle.fileno())
        os.replace(temporary_path, artifact_paths[name])

    metadata["artifact_sha256"] = {
        name: _sha256_file(path) for name, path in artifact_paths.items()
    }
    metadata_bytes = json.dumps(metadata, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    _atomic_write(output_dir / "METADATA.json", metadata_bytes)
    thresholds_bytes = (
        json.dumps(thresholds, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )
    _atomic_write(output_dir / "THRESHOLDS.json", thresholds_bytes)


def bootstrap(dataset_dir=DATASET_DIR, model_dir=MODEL_DIR, seed=42):
    """Train and deploy an initial model from the base synthetic data only."""
    human_rows, _ = _read_base_data(dataset_dir)
    scaler = StandardScaler()
    scaled_humans = scaler.fit_transform(human_rows[FEATURES].to_numpy(dtype=float))
    model = IsolationForest(
        n_estimators=MODEL_PARAMS["n_estimators"],
        contamination=MODEL_PARAMS["contamination"],
        random_state=seed,
        n_jobs=MODEL_PARAMS["n_jobs"],
    )
    model.fit(scaled_humans)

    training_csv = Path(dataset_dir) / "training_data.csv"
    human_csv = Path(dataset_dir) / "human_only.csv"
    training_hash = _sha256_file(training_csv)
    human_hash = _sha256_file(human_csv)
    model_version = f"bootstrap-{training_hash[:12]}-{seed}"
    thresholds = {
        **DEFAULT_THRESHOLDS,
        "model_version": model_version,
    }
    metadata = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "feature_names": FEATURES,
        "model_params": {**MODEL_PARAMS, "random_state": seed},
        "seed": seed,
        "row_counts": {
            "base_human": int(len(human_rows)),
            "real_human": 0,
            "feedback_human": 0,
        },
        "training_csv_sha256": {
            "training_data.csv": training_hash,
            "human_only.csv": human_hash,
        },
        "git_commit": _git_commit(),
        "canary_metrics": {"available": False, "reason": "Bootstrap has no canary set."},
        "thresholds": DEFAULT_THRESHOLDS,
    }
    _save_bundle(model, scaler, metadata, thresholds, model_dir)
    return metadata


def _feedback_frame(rows, label, min_feedback):
    """Validate exported label rows and return their feature-only frame."""
    if not isinstance(rows, list) or len(rows) < min_feedback:
        raise InsufficientFeedbackError(
            f"At least {min_feedback} verified {label} examples are required."
        )
    validated_rows = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("features"), dict):
            raise ValueError(f"Every {label} feedback row must contain a feature object.")
        validated_rows.append(validate_features(row["features"]))
    return pd.DataFrame(validated_rows, columns=FEATURES)


def _score_rows(model, scaler, rows):
    """Score one feature frame with a candidate bundle."""
    transformed = scaler.transform(rows[FEATURES].to_numpy(dtype=float))
    scores = np.asarray(model.decision_function(transformed), dtype=float)
    if not np.isfinite(scores).all():
        raise ModelQualityError("Candidate model produced non-finite canary scores.")
    return scores


def _derive_thresholds(human_scores):
    """Set a CAPTCHA boundary that preserves at least 95% human allow rate."""
    sorted_scores = np.sort(np.asarray(human_scores, dtype=float))
    if not len(sorted_scores) or not np.isfinite(sorted_scores).all():
        raise ModelQualityError("Human canary scores are missing or non-finite.")
    challenge_count = max(1, int(np.floor(len(sorted_scores) * 0.05)))
    challenge_count = min(challenge_count, len(sorted_scores) - 1)
    captcha_below = float(np.nextafter(sorted_scores[challenge_count], -np.inf))
    block_below = float(np.nextafter(sorted_scores[0], -np.inf))
    if block_below >= captcha_below:
        block_below = float(np.nextafter(captcha_below, -np.inf))
    return {"block_below": block_below, "captcha_below": captcha_below}


def _backup_bundle(model_dir, model_version):
    """Copy the current verified bundle before replacing any artifact."""
    output_dir = Path(model_dir)
    backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_dir = output_dir / "BACKUPS" / f"{model_version}-{backup_id}"
    existing_files = [output_dir / name for name in BUNDLE_FILES if (output_dir / name).exists()]
    if not existing_files:
        return None
    backup_dir.mkdir(parents=True, exist_ok=False)
    for source in existing_files:
        shutil.copy2(source, backup_dir / source.name)
    return backup_dir


def _restore_bundle(model_dir, backup_dir):
    """Restore the prior bundle after any failed candidate write or validation."""
    output_dir = Path(model_dir)
    for name in BUNDLE_FILES:
        destination = output_dir / name
        backup = backup_dir / name if backup_dir is not None else None
        if backup is not None and backup.exists():
            _atomic_write(destination, backup.read_bytes())
        elif destination.exists():
            destination.unlink()


def retrain(
    feedback_human,
    feedback_bot,
    dataset_dir=DATASET_DIR,
    model_dir=MODEL_DIR,
    min_feedback=20,
    seed=42,
    dry_run=False,
):
    """Train on verified humans, evaluate a held-out canary, then publish safely."""
    if isinstance(min_feedback, bool) or not isinstance(min_feedback, int) or min_feedback < 1:
        raise ValueError("min_feedback must be a positive integer.")
    base_humans, _ = _read_base_data(dataset_dir)
    human_feedback = _feedback_frame(feedback_human, "human", min_feedback)
    bot_feedback = _feedback_frame(feedback_bot, "bot", min_feedback)
    base_train, canary_humans = train_test_split(
        base_humans[FEATURES],
        test_size=0.2,
        random_state=seed,
    )
    training_humans = pd.concat([base_train, human_feedback], ignore_index=True)

    scaler = StandardScaler()
    scaled_humans = scaler.fit_transform(training_humans[FEATURES].to_numpy(dtype=float))
    model = IsolationForest(
        n_estimators=MODEL_PARAMS["n_estimators"],
        contamination=MODEL_PARAMS["contamination"],
        random_state=seed,
        n_jobs=MODEL_PARAMS["n_jobs"],
    )
    model.fit(scaled_humans)

    human_scores = _score_rows(model, scaler, canary_humans)
    bot_scores = _score_rows(model, scaler, bot_feedback)
    thresholds = _derive_thresholds(human_scores)
    human_verdicts = [route_score(score, thresholds) for score in human_scores]
    allowed_rate = 100.0 * human_verdicts.count("allowed") / len(human_verdicts)
    blocked_rate = 100.0 * human_verdicts.count("blocked") / len(human_verdicts)
    bot_blocked_rate = 100.0 * sum(
        score < thresholds["block_below"] for score in bot_scores
    ) / len(bot_scores)
    canary_metrics = {
        "available": True,
        "human_samples": len(human_scores),
        "human_allowed_rate": allowed_rate,
        "human_captcha_rate": 100.0 * human_verdicts.count("captcha") / len(human_verdicts),
        "human_blocked_rate": blocked_rate,
        "bot_samples": len(bot_scores),
        "bot_blocked_rate": bot_blocked_rate,
    }
    if (
        allowed_rate < QUALITY_GATE_MIN_ALLOWED_RATE
        or blocked_rate > QUALITY_GATE_MAX_BLOCKED_RATE
    ):
        raise ModelQualityError(
            "Candidate failed canary gate: human allow rate must be at least 95% "
            "and blocked rate must be 0%."
        )

    human_feedback_data = human_feedback[FEATURES].to_dict(orient="records")
    bot_feedback_data = bot_feedback[FEATURES].to_dict(orient="records")
    feedback_hash = hashlib.sha256(
        json.dumps(
            {"human": human_feedback_data, "bot": bot_feedback_data, "seed": seed},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    model_version = f"retrain-{feedback_hash[:12]}-{seed}"
    thresholds["model_version"] = model_version
    training_csv = Path(dataset_dir) / "training_data.csv"
    human_csv = Path(dataset_dir) / "human_only.csv"
    metadata = {
        "model_version": model_version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "python_version": sys.version.split()[0],
        "numpy_version": np.__version__,
        "scikit_learn_version": sklearn.__version__,
        "feature_names": FEATURES,
        "model_params": {**MODEL_PARAMS, "random_state": seed},
        "seed": seed,
        "row_counts": {
            "base_human": int(len(base_train)),
            "canary_human": int(len(canary_humans)),
            "real_human": 0,
            "feedback_human": len(human_feedback),
            "feedback_bot": len(bot_feedback),
        },
        "training_csv_sha256": {
            "training_data.csv": _sha256_file(training_csv),
            "human_only.csv": _sha256_file(human_csv),
        },
        "feedback_sha256": feedback_hash,
        "git_commit": _git_commit(),
        "canary_metrics": canary_metrics,
        "thresholds": {
            "block_below": thresholds["block_below"],
            "captcha_below": thresholds["captcha_below"],
        },
    }

    output_dir = Path(model_dir)
    if dry_run:
        return {
            "model_version": model_version,
            "deployed": False,
            "canary_metrics": canary_metrics,
            "row_counts": metadata["row_counts"],
        }

    backup_dir = _backup_bundle(output_dir, model_version)
    deployed = False
    try:
        _save_bundle(model, scaler, metadata, thresholds, output_dir)
        candidate = MLEngine(output_dir)
        if candidate.degraded or candidate.get_status()["model_version"] != model_version:
            raise ModelQualityError("Candidate bundle failed integrity validation.")
        deployed = True
    finally:
        if not deployed:
            _restore_bundle(output_dir, backup_dir)

    return {
        "model_version": model_version,
        "deployed": True,
        "backup_id": backup_dir.name if backup_dir is not None else None,
        "canary_metrics": canary_metrics,
        "row_counts": metadata["row_counts"],
    }


def main():
    """Run bootstrap or a retraining experiment from exported feedback CSVs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--min-feedback", type=int, default=20)
    parser.add_argument("--feedback-human", type=Path)
    parser.add_argument("--feedback-bot", type=Path)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.bootstrap:
        metadata = bootstrap(dataset_dir=args.dataset_dir, model_dir=args.model_dir, seed=args.seed)
        print(f"Bootstrapped model version {metadata['model_version']}")
        return
    if args.feedback_human is None or args.feedback_bot is None:
        parser.error("Retraining requires --feedback-human and --feedback-bot CSV files.")

    def load_feedback(path):
        frame = pd.read_csv(path)
        if frame.columns.tolist() != FEATURES:
            raise ValueError(f"{path} columns do not match the feature contract.")
        return [{"features": validate_features(row)} for row in frame.to_dict(orient="records")]

    result = retrain(
        load_feedback(args.feedback_human),
        load_feedback(args.feedback_bot),
        dataset_dir=args.dataset_dir,
        model_dir=args.model_dir,
        min_feedback=args.min_feedback,
        seed=args.seed,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
