"""Tests for deterministic model bootstrap and artifact metadata."""

import json
import os
import sys

import numpy as np

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from ML.TRAINING import BUILD_DATASET, RETRAIN


def test_bootstrap_writes_model_bundle_and_metadata(tmp_path):
    """Bootstrap writes hashed artifacts and thresholds as the bundle signal."""
    dataset_dir = tmp_path / "dataset"
    model_dir = tmp_path / "models"
    BUILD_DATASET.write_dataset(dataset_dir)

    metadata = RETRAIN.bootstrap(dataset_dir, model_dir)

    thresholds = json.loads((model_dir / "THRESHOLDS.json").read_text(encoding="utf-8"))
    stored_metadata = json.loads((model_dir / "METADATA.json").read_text(encoding="utf-8"))
    assert metadata["feature_names"] == RETRAIN.FEATURES
    assert stored_metadata["artifact_sha256"]["aethercept_model.pkl"]
    assert stored_metadata["training_csv_sha256"]["human_only.csv"]
    assert thresholds["model_version"] == metadata["model_version"]
    assert thresholds["block_below"] == -0.14
    assert thresholds["captcha_below"] == -0.015
    assert np.isfinite(metadata["row_counts"]["base_human"])


def test_bootstrap_rejects_wrong_human_feature_columns(tmp_path):
    """Training stops rather than silently accepting a mismatched schema."""
    dataset_dir = tmp_path / "dataset"
    dataset_dir.mkdir()
    (dataset_dir / "human_only.csv").write_text("wrong\n1\n", encoding="utf-8")
    (dataset_dir / "training_data.csv").write_text("label\nhuman\n", encoding="utf-8")

    try:
        RETRAIN.bootstrap(dataset_dir, tmp_path / "models")
    except ValueError as error:
        assert "columns" in str(error)
    else:
        raise AssertionError("Bootstrap accepted an invalid feature schema.")
