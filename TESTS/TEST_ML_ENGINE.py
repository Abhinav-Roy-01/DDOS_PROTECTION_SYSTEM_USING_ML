"""Tests for ML feature validation, model integrity, and score routing."""

import json
import os
import sys

import numpy as np
import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT_DIR)

from API import ML_ENGINE
from ML.TRAINING import BUILD_DATASET, RETRAIN


@pytest.fixture
def model_dir(tmp_path):
    """Create a fresh, bootstrapped model in a temporary directory."""
    dataset_dir = tmp_path / "dataset"
    model_path = tmp_path / "models"
    BUILD_DATASET.write_dataset(dataset_dir)
    RETRAIN.bootstrap(dataset_dir=dataset_dir, model_dir=model_path)
    return model_path


def _human_fixture():
    """Return the historical human fixture converted to entropy nats."""
    return {
        "click_count": 8,
        "avg_click_interval": 1524.9435637982203,
        "click_interval_variance": 269875.23591802106,
        "click_interval_entropy": 2.304229902307089 * np.log(2),
        "mouse_velocity_variance": 0.3561481826419697,
        "max_element_click_rate": 1.2012582857050627,
        "scroll_events": 11,
        "keystroke_count": 5,
    }


def _bot_fixture():
    """Return the historical flooder fixture converted to entropy nats."""
    return {
        "click_count": 200,
        "avg_click_interval": 22.60973187772914,
        "click_interval_variance": 6.132684489013476,
        "click_interval_entropy": 0.014982035810896866 * np.log(2),
        "mouse_velocity_variance": 0.0,
        "max_element_click_rate": 39.29298216437756,
        "scroll_events": 0,
        "keystroke_count": 0,
    }


def test_validate_features_orders_required_numeric_values_and_ignores_extras():
    """Feature validation returns the fixed model order and ignores extra keys."""
    features = {**_human_fixture(), "ignored": "extra"}

    validated = ML_ENGINE.validate_features(features)

    assert list(validated) == ML_ENGINE.FEATURES
    assert validated["click_count"] == 8.0


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("click_count"),
        lambda value: value.update(click_count="8"),
        lambda value: value.update(click_count=True),
        lambda value: value.update(click_count=float("nan")),
        lambda value: value.update(click_count=float("inf")),
        lambda value: value.update(click_count=-1),
        lambda value: value.update(click_count=10_001),
        lambda value: value.update(avg_click_interval=3_600_001),
        lambda value: value.update(scroll_events=100_001),
        lambda value: value.update(keystroke_count=100_001),
    ],
)
def test_validate_features_rejects_invalid_values(mutation):
    """Invalid or excessive telemetry values fail before model scoring."""
    features = _human_fixture()
    mutation(features)

    with pytest.raises(ML_ENGINE.FeatureValidationError):
        ML_ENGINE.validate_features(features)


def test_route_score_includes_captcha_threshold_boundaries():
    """Scores at either configured threshold enter the CAPTCHA band."""
    thresholds = {"block_below": -0.055, "captcha_below": -0.015}

    assert ML_ENGINE.route_score(-0.056, thresholds) == "blocked"
    assert ML_ENGINE.route_score(-0.055, thresholds) == "captcha"
    assert ML_ENGINE.route_score(-0.015, thresholds) == "captcha"
    assert ML_ENGINE.route_score(-0.014, thresholds) == "allowed"


def test_bootstrapped_model_routes_the_known_human_and_bot(model_dir):
    """The converted reference human is allowed and the HTTP flooder is blocked."""
    engine = ML_ENGINE.MLEngine(model_dir)

    human = engine.predict(_human_fixture())
    bot = engine.predict(_bot_fixture())

    assert human["verdict"] == "allowed"
    assert bot["verdict"] == "blocked"
    assert human["score"] > bot["score"]
    assert human["model_version"].startswith("bootstrap-")


def test_missing_or_corrupt_model_starts_degraded(tmp_path):
    """A missing or invalid model does not prevent app startup."""
    engine = ML_ENGINE.MLEngine(tmp_path)

    assert engine.degraded is True
    assert engine.get_thresholds() == ML_ENGINE.DEFAULT_THRESHOLDS
    with pytest.raises(ML_ENGINE.ModelUnavailableError):
        engine.predict(_human_fixture())


def test_artifact_hash_mismatch_is_rejected(model_dir):
    """A modified pickle is never loaded when its recorded hash differs."""
    model_path = model_dir / "aethercept_model.pkl"
    model_path.write_bytes(model_path.read_bytes() + b"tampered")

    engine = ML_ENGINE.MLEngine(model_dir)

    assert engine.degraded is True


def test_invalid_thresholds_fall_back_to_seed_values(tmp_path):
    """Invalid threshold JSON falls back to safe bootstrap thresholds."""
    (tmp_path / "THRESHOLDS.json").write_text(
        json.dumps({"block_below": 1, "captcha_below": -1}),
        encoding="utf-8",
    )

    engine = ML_ENGINE.MLEngine(tmp_path)

    assert engine.get_thresholds() == ML_ENGINE.DEFAULT_THRESHOLDS


def test_forced_reload_swaps_model_version_and_thresholds(model_dir):
    """A new version signal reloads the verified model bundle in this worker."""
    engine = ML_ENGINE.MLEngine(model_dir)
    metadata_path = model_dir / "METADATA.json"
    thresholds_path = model_dir / "THRESHOLDS.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    metadata["model_version"] = "bootstrap-reloaded"
    thresholds["model_version"] = "bootstrap-reloaded"
    thresholds["block_below"] = 1.0
    thresholds["captcha_below"] = 2.0
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
    thresholds_path.write_text(json.dumps(thresholds), encoding="utf-8")

    assert engine.reload_model(force=True) is True
    assert engine.get_status()["model_version"] == "bootstrap-reloaded"
    assert engine.predict(_human_fixture())["verdict"] == "blocked"
