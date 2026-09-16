"""
RETRAIN.PY -- feedback -> retrain loop.

PHASE: 4 (running it against real traffic; the code itself is a straight
          copy from the prototype)
REUSE: copy as-is from old project's ML/TRAINING/RETRAIN.py -- see
       DOCS/REUSE_MAP.md. Double check path constants (DATASET_DIR,
       MODELS_DIR, etc.) still resolve correctly at this folder depth.

WHAT GOES HERE:
    - Folds ML/DATASET/feedback_human.csv into human_only.csv
    - Refits IsolationForest + StandardScaler (same hyperparameters as
      the original notebook: n_estimators=100, contamination=0.01)
    - Re-derives block/captcha thresholds via brute-force grid search
      against real scored data
    - Quality gate: refuses to deploy unless >=95% human-allowed, 0%
      human-blocked
    - Atomic deploy + backup + feedback archival + retrain_log.jsonl

NOT YET IMPLEMENTED (pending Phase 2 dataset copy).
"""
