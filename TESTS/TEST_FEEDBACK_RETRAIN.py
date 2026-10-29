"""Tests for quality-gated retraining with verified feedback rows."""

import json
import os
import sys

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from API.ML_ENGINE import FEATURES, MLEngine
from ML.TRAINING import BUILD_DATASET, RETRAIN


@pytest.fixture
def retrain_fixture(tmp_path):
    dataset_dir = tmp_path / "dataset"
    model_dir = tmp_path / "models"
    dataset = BUILD_DATASET.write_dataset(dataset_dir)
    RETRAIN.bootstrap(dataset_dir=dataset_dir, model_dir=model_dir)

    def rows(label, count=20):
        examples = dataset.loc[dataset["label"] == label, FEATURES].head(count)
        return [{"features": row} for row in examples.to_dict(orient="records")]

    return dataset_dir, model_dir, rows


def _bundle_bytes(model_dir):
    return {
        name: (model_dir / name).read_bytes()
        for name in RETRAIN.BUNDLE_FILES
    }


def test_retrain_passes_canary_gate_backs_up_and_deploys(retrain_fixture):
    dataset_dir, model_dir, rows = retrain_fixture

    result = RETRAIN.retrain(
        rows("human"),
        rows("bot"),
        dataset_dir=dataset_dir,
        model_dir=model_dir,
        min_feedback=20,
    )

    assert result["deployed"] is True
    assert result["canary_metrics"]["human_allowed_rate"] >= 95.0
    assert result["canary_metrics"]["human_blocked_rate"] == 0.0
    assert result["backup_id"]
    backup_dir = model_dir / "BACKUPS" / result["backup_id"]
    assert all((backup_dir / name).exists() for name in RETRAIN.BUNDLE_FILES)
    assert MLEngine(model_dir).get_status()["model_version"] == result["model_version"]
    metadata = json.loads((model_dir / "METADATA.json").read_text(encoding="utf-8"))
    assert metadata["canary_metrics"] == result["canary_metrics"]
    assert metadata["row_counts"]["feedback_human"] == 20
    assert metadata["row_counts"]["feedback_bot"] == 20


def test_retrain_dry_run_does_not_change_the_active_bundle(retrain_fixture):
    dataset_dir, model_dir, rows = retrain_fixture
    original = _bundle_bytes(model_dir)

    result = RETRAIN.retrain(
        rows("human"),
        rows("bot"),
        dataset_dir=dataset_dir,
        model_dir=model_dir,
        min_feedback=20,
        dry_run=True,
    )

    assert result["deployed"] is False
    assert _bundle_bytes(model_dir) == original


def test_retrain_rejects_insufficient_verified_feedback(retrain_fixture):
    dataset_dir, model_dir, rows = retrain_fixture
    original = _bundle_bytes(model_dir)

    with pytest.raises(RETRAIN.InsufficientFeedbackError):
        RETRAIN.retrain(
            rows("human", 19),
            rows("bot"),
            dataset_dir=dataset_dir,
            model_dir=model_dir,
            min_feedback=20,
        )

    assert _bundle_bytes(model_dir) == original


def test_retrain_restores_the_previous_bundle_when_save_fails(retrain_fixture, monkeypatch):
    dataset_dir, model_dir, rows = retrain_fixture
    original = _bundle_bytes(model_dir)

    def partial_write(*_args, **_kwargs):
        (model_dir / "METADATA.json").write_text("invalid", encoding="utf-8")
        raise OSError("simulated write failure")

    monkeypatch.setattr(RETRAIN, "_save_bundle", partial_write)
    with pytest.raises(OSError, match="simulated write failure"):
        RETRAIN.retrain(
            rows("human"),
            rows("bot"),
            dataset_dir=dataset_dir,
            model_dir=model_dir,
            min_feedback=20,
        )

    assert _bundle_bytes(model_dir) == original
