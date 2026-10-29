"""Bootstrap a verified production-format IsolationForest model bundle."""

import argparse
import hashlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

ROOT_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = ROOT_DIR / "ML" / "DATASET"
MODEL_DIR = ROOT_DIR / "ML" / "MODELS"
API_DIR = ROOT_DIR / "API"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from API.ML_ENGINE import DEFAULT_THRESHOLDS, FEATURES

MODEL_PARAMS = {
    "n_estimators": 100,
    "contamination": 0.01,
    "random_state": 42,
    "n_jobs": 1,
}


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


def main():
    """Run the explicitly requested bootstrap command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if not args.bootstrap:
        parser.error("Only --bootstrap is implemented in this phase.")
    metadata = bootstrap(seed=args.seed)
    print(f"Bootstrapped model version {metadata['model_version']}")


if __name__ == "__main__":
    main()
