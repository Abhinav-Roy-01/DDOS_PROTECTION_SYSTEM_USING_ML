"""
ML_ENGINE.PY -- Loads the trained model/scaler, exposes prediction + thresholds.

PHASE: 2
REUSE: copy as-is from old project's API/ml_engine.py (just rename) -- see DOCS/REUSE_MAP.md

WHAT GOES HERE:
    - MLEngine class: loads ML/MODELS/aethercept_model.pkl + aethercept_scaler.pkl
    - predict(features_dict) -> {prediction, anomaly_score}
    - get_thresholds() -- reads ML/MODELS/THRESHOLDS.json, falls back to
      DEFAULT_THRESHOLDS if missing/corrupt
    - reload_model() -- hot-swap after a retrain deploys

NOT YET IMPLEMENTED.
"""
