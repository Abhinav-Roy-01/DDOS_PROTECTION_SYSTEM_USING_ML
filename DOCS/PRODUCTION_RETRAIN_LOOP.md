# The feedback / retrain loop

(Reused from the earlier prototype — logic unchanged, paths updated for
the new scaffold where `FEEDBACK/` is a top-level folder, not nested
under `API/`.)

## Implemented flow

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
      - QUALITY GATE: refuses to deploy unless >=95% of held-out base
        humans are allowed and 0% are blocked outright
      - on success: backs up old model/scaler/thresholds under
        ML/MODELS/BACKUPS/, atomically swaps in the verified bundle, and
        consumes only the exported feedback rows
```

Only two outcomes are trusted as labels: a ban that stuck, and a CAPTCHA
a human actually solved. Raw `/predict` guesses are never fed back.

## Running it

**On demand (admin key and allowlisted source IP required):**
```
POST /api/retrain/start
GET  /api/retrain/status
GET  /api/feedback/stats
```

The retraining request is synchronous, takes a shared Redis lock, requires
at least 20 verified examples of each label, and restores exported feedback
if a candidate is rejected or a dry-run is requested. The runner reloads a
successfully deployed model in the serving process.

**On a schedule:**
```
0 3 * * *  ADMIN_API_KEY=... python SCRIPTS/RETRAIN/RETRAIN_SCHEDULER.py --once
```

**Manually, for debugging:**
```
python ML/TRAINING/RETRAIN.py --dry-run --feedback-human feedback_human.csv --feedback-bot feedback_bot.csv
```

`--dry-run` exercises training and canary validation without changing the
active model bundle.
