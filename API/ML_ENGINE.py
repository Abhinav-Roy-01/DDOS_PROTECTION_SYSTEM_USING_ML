"""Load the verified model bundle and score validated browser features."""

import hashlib
import json
import logging
import math
import pickle
import threading
import time
from numbers import Real
from pathlib import Path

import sklearn

logger = logging.getLogger(__name__)

FEATURES = [
    "click_count",
    "avg_click_interval",
    "click_interval_variance",
    "click_interval_entropy",
    "mouse_velocity_variance",
    "max_element_click_rate",
    "scroll_events",
    "keystroke_count",
]
DEFAULT_THRESHOLDS = {"block_below": -0.055, "captcha_below": -0.015}
MODEL_FILES = ("aethercept_model.pkl", "aethercept_scaler.pkl")
MODEL_DIR = Path(__file__).resolve().parents[1] / "ML" / "MODELS"
RELOAD_INTERVAL_SECONDS = 5
MAX_CLICK_COUNT = 10_000
MAX_INTERVAL_MS = 3_600_000
MAX_EVENT_COUNT = 100_000


class FeatureValidationError(ValueError):
    """Raised when a telemetry feature is missing or outside its allowed range."""


class ModelUnavailableError(RuntimeError):
    """Raised when no verified model is available for scoring."""


class ModelArtifactError(ValueError):
    """Raised when a saved model bundle fails its integrity checks."""


def validate_features(features):
    """Validate required numeric features and return them in canonical order."""
    if not isinstance(features, dict):
        raise FeatureValidationError("Body must be a JSON object.")

    missing = [name for name in FEATURES if name not in features]
    if missing:
        raise FeatureValidationError(f"Missing required features: {', '.join(missing)}.")

    validated = {}
    for name in FEATURES:
        value = features[name]
        if isinstance(value, bool) or not isinstance(value, Real):
            raise FeatureValidationError(f"Feature '{name}' must be a number.")
        numeric_value = float(value)
        if not math.isfinite(numeric_value) or numeric_value < 0:
            raise FeatureValidationError(f"Feature '{name}' must be finite and non-negative.")
        validated[name] = numeric_value

    if validated["click_count"] > MAX_CLICK_COUNT:
        raise FeatureValidationError("Feature 'click_count' exceeds its maximum.")
    if validated["avg_click_interval"] > MAX_INTERVAL_MS:
        raise FeatureValidationError("Feature 'avg_click_interval' exceeds its maximum.")
    for name in ("scroll_events", "keystroke_count"):
        if validated[name] > MAX_EVENT_COUNT:
            raise FeatureValidationError(f"Feature '{name}' exceeds its maximum.")
    return validated


def route_score(score, thresholds):
    """Map one anomaly score to the configured allow, CAPTCHA, or block verdict."""
    if score < thresholds["block_below"]:
        return "blocked"
    if score <= thresholds["captcha_below"]:
        return "captcha"
    return "allowed"


def _read_thresholds(model_dir):
    """Read valid thresholds or return the documented seed values."""
    path = model_dir / "THRESHOLDS.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        block_below = data["block_below"]
        captcha_below = data["captcha_below"]
        if (
            isinstance(block_below, bool)
            or isinstance(captcha_below, bool)
            or not isinstance(block_below, Real)
            or not isinstance(captcha_below, Real)
            or not math.isfinite(block_below)
            or not math.isfinite(captcha_below)
            or block_below >= captcha_below
        ):
            raise ValueError("Threshold values are invalid.")
        result = {
            "block_below": float(block_below),
            "captcha_below": float(captcha_below),
        }
        version = data.get("model_version")
        if isinstance(version, str) and version:
            result["model_version"] = version
        return result
    except (OSError, ValueError, TypeError, KeyError) as error:
        logger.warning("Using default ML thresholds: %s", error)
        return dict(DEFAULT_THRESHOLDS)


def _sha256_file(path):
    """Return the SHA-256 digest of one model artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MLEngine:
    """Manage a verified model bundle and its periodically refreshed thresholds."""

    def __init__(self, model_dir=MODEL_DIR):
        """Load model files from a trusted directory, or start in degraded mode."""
        self.model_dir = Path(model_dir)
        self._lock = threading.RLock()
        self._model = None
        self._scaler = None
        self._thresholds = _read_thresholds(self.model_dir)
        self._model_version = self._thresholds.get("model_version")
        self._degraded = True
        self._last_check = 0.0
        self._threshold_mtime_ns = None
        self._load_initial_bundle()

    @property
    def degraded(self):
        """Return whether the engine has no verified model bundle."""
        return self._degraded

    def get_status(self):
        """Return model health without exposing file paths or sensitive inputs."""
        return {
            "degraded": self._degraded,
            "model_version": self._model_version,
            "thresholds": self.get_thresholds(),
        }

    def get_thresholds(self):
        """Return a copy of the active routing thresholds."""
        return dict(self._thresholds)

    def _read_bundle(self):
        """Verify and load the model, scaler, metadata, and routing thresholds."""
        metadata_path = self.model_dir / "METADATA.json"
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("feature_names") != FEATURES:
            raise ModelArtifactError("Model feature names do not match the live feature contract.")

        thresholds = _read_thresholds(self.model_dir)
        version = metadata.get("model_version")
        if not isinstance(version, str) or not version:
            raise ModelArtifactError("Model metadata has no model version.")
        threshold_version = thresholds.get("model_version")
        if threshold_version is not None and threshold_version != version:
            raise ModelArtifactError("Threshold and model versions do not match.")

        artifact_hashes = metadata.get("artifact_sha256")
        if not isinstance(artifact_hashes, dict):
            raise ModelArtifactError("Model metadata has no artifact hashes.")
        artifact_paths = {name: self.model_dir / name for name in MODEL_FILES}
        for name, path in artifact_paths.items():
            expected_hash = artifact_hashes.get(name)
            if not isinstance(expected_hash, str) or _sha256_file(path) != expected_hash:
                raise ModelArtifactError(f"Model artifact integrity check failed for {name}.")

        with artifact_paths[MODEL_FILES[0]].open("rb") as file_handle:
            model = pickle.load(file_handle)
        with artifact_paths[MODEL_FILES[1]].open("rb") as file_handle:
            scaler = pickle.load(file_handle)
        if not callable(getattr(model, "decision_function", None)):
            raise ModelArtifactError("Model does not provide decision_function.")
        if not callable(getattr(scaler, "transform", None)):
            raise ModelArtifactError("Scaler does not provide transform.")

        trained_version = metadata.get("scikit_learn_version")
        if trained_version and trained_version != sklearn.__version__:
            logger.warning(
                "Model was trained with scikit-learn %s; runtime is %s.",
                trained_version,
                sklearn.__version__,
            )
        thresholds["model_version"] = version
        return model, scaler, metadata, thresholds

    def _load_initial_bundle(self):
        """Load the initial bundle and leave the process healthy if it is absent."""
        try:
            model, scaler, _, thresholds = self._read_bundle()
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ImportError,
            pickle.PickleError,
            EOFError,
        ) as error:
            logger.warning("ML model unavailable; starting in degraded mode: %s", error)
            return

        with self._lock:
            self._model = model
            self._scaler = scaler
            self._thresholds = thresholds
            self._model_version = thresholds["model_version"]
            self._degraded = False
            self._record_threshold_mtime()

    def _record_threshold_mtime(self):
        """Remember the current thresholds file timestamp for reload polling."""
        try:
            self._threshold_mtime_ns = (self.model_dir / "THRESHOLDS.json").stat().st_mtime_ns
        except OSError:
            self._threshold_mtime_ns = None

    def reload_model(self, force=False):
        """Reload a changed, verified bundle when its version signal has changed."""
        now = time.monotonic()
        with self._lock:
            if not force and now - self._last_check < RELOAD_INTERVAL_SECONDS:
                return False
            self._last_check = now

            try:
                threshold_mtime = (self.model_dir / "THRESHOLDS.json").stat().st_mtime_ns
            except OSError as error:
                logger.warning("Cannot inspect model version signal: %s", error)
                return False
            if not force and threshold_mtime == self._threshold_mtime_ns:
                return False

            try:
                model, scaler, _, thresholds = self._read_bundle()
            except (
                OSError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                ImportError,
                pickle.PickleError,
                EOFError,
            ) as error:
                logger.warning("Model reload rejected; retaining active bundle: %s", error)
                return False

            changed = thresholds["model_version"] != self._model_version
            self._model = model
            self._scaler = scaler
            self._thresholds = thresholds
            self._model_version = thresholds["model_version"]
            self._degraded = False
            self._threshold_mtime_ns = threshold_mtime
            return changed or force

    def predict(self, features):
        """Validate one feature vector and return its score and routing verdict."""
        validated = validate_features(features)
        self.reload_model()
        with self._lock:
            model = self._model
            scaler = self._scaler
            thresholds = dict(self._thresholds)
            model_version = self._model_version
        if model is None or scaler is None:
            raise ModelUnavailableError("No verified model is available.")

        row = [[validated[name] for name in FEATURES]]
        scaled = scaler.transform(row)
        score = float(model.decision_function(scaled)[0])
        if not math.isfinite(score):
            raise ModelUnavailableError("The model returned a non-finite score.")
        return {
            "verdict": route_score(score, thresholds),
            "score": score,
            "model_version": model_version,
        }
