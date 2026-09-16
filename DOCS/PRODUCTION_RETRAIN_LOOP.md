# The feedback / retrain loop

(Reused from the earlier prototype — logic unchanged, paths updated for
the new scaffold where `FEEDBACK/` is a top-level folder, not nested
under `API/`.)

## How it works

```
/predict scores a request (API/SERVER.py)
        │
        ▼
FEEDBACK/FEEDBACK_STORE.record_pending(ip, features)
        │
  ┌─────┴──────┐
  ▼            ▼
score <       score in
block_below   captcha band -> CAPTCHA served -> solved correctly
  │                                  │
  ▼                                  ▼
manual_ban(ip)              CAPTCHA/CAPTCHA_ROUTES.verify() succeeds
label_as_bot(ip)             label_as_human(ip)
  │                                  │
  ▼                                  ▼
ML/DATASET/feedback_bot.csv   ML/DATASET/feedback_human.csv
  │                                  │
  └─────────────┬────────────────────┘
                 ▼
      ML/TRAINING/RETRAIN.py
      - folds feedback_human.csv into human_only.csv
      - refits IsolationForest + StandardScaler
      - re-derives block/captcha thresholds against real scored data
      - QUALITY GATE: refuses to deploy unless >=95% of humans are
        allowed and 0% are blocked outright
      - on success: backs up old model/scaler/thresholds under
        ML/MODELS/BACKUPS/, atomically swaps in new ones, archives
        consumed feedback CSVs under ML/DATASET/ARCHIVE/, logs to
        ML/MODELS/retrain_log.jsonl
```

Only two outcomes are trusted as labels: a ban that stuck, and a CAPTCHA
a human actually solved. Raw `/predict` guesses are never fed back.

## Running it

**On demand:**
```
POST /api/retrain/start
GET  /api/retrain/status
GET  /api/feedback/stats
```

**On a schedule (production):**
```
0 3 * * *  /path/to/venv/bin/python SCRIPTS/RETRAIN/RETRAIN_SCHEDULER.py --once --min-feedback 20
```

**Manually, for debugging:**
```
cd ML/TRAINING
python RETRAIN.py --dry-run
python RETRAIN.py --min-feedback 20
```

## Built in Phase 4 of the roadmap

This loop's code already exists (carried over from the prototype); Phase
4 is about running it against REAL production traffic for the first
time, not writing it from scratch.
