"""
RETRAIN_RUNNER.PY -- bridges the Flask app to ML/TRAINING/RETRAIN.py.

PHASE: 4
REUSE: copy as-is from old project's API/RETRAIN_RUNNER.py, moved to
       FEEDBACK/ -- see DOCS/REUSE_MAP.md.

WHAT GOES HERE:
    - start_retrain() -- runs RETRAIN.py as a background subprocess so
      the admin endpoint returns immediately
    - get_status() -- idle/running + last result
    - Reloads ML_ENGINE after a successful deploy

NOT YET IMPLEMENTED.
"""
