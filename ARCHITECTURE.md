# Architecture

## Request flow (target end state, after Phase 3)

```
                              INTERNET
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  nginx (reverse proxy)  │
                    │  - limit_req (rate)     │
                    │  - limit_conn (slowloris)│
                    │  - HTTPS termination    │
                    └───────────┬─────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │  gunicorn (4 workers)   │
                    │  running API/SERVER.py  │
                    └───────────┬─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    ▼                           ▼
          ┌──────────────────┐       ┌──────────────────┐
          │  Redis            │       │  ML/MODELS/       │
          │  - rate limits    │       │  aethercept model  │
          │  - ban list        │       │  + THRESHOLDS.json │
          │  - captcha state   │       └──────────────────┘
          │  - feedback pending│
          └──────────────────┘
                    │
                    ▼
          ┌──────────────────────────┐
          │  FEEDBACK/FEEDBACK_STORE  │
          │  -> banned IP => bot row  │
          │  -> captcha-pass => human │
          └────────────┬──────────────┘
                        ▼
          ┌──────────────────────────┐
          │  ML/TRAINING/RETRAIN.py   │
          │  (systemd timer, daily)   │
          │  - quality-gated deploy   │
          └──────────────────────────┘
```

## Why each piece exists

- **nginx** — first line of defense. Handles raw connection-level abuse
  (Slowloris, basic floods) before it ever reaches Python. This is
  cheaper and faster than doing it in application code.
- **Redis** — shared state across gunicorn workers. Without this, each
  worker has its own rate limits/ban list and an attacker can dodge
  bans by hitting a different worker.
- **gunicorn** — the Flask dev server (`app.run(debug=True)`) is single-
  threaded and not meant to face real traffic.
- **ML engine** — behavioral scoring for requests that DO reach the app
  (i.e., survived nginx + rate limiting). Only useful where a client
  executes JS and submits telemetry — see `DOCS/LIMITATIONS.md`.
- **Feedback loop** — turns real outcomes (a ban that stuck, a CAPTCHA a
  human solved) into labeled data for the next retrain, without
  retraining on the model's own unverified guesses.

## What's explicitly NOT in this architecture

Network-level (L3/L4) volumetric attack mitigation. That requires
CDN/anycast/ISP-level scrubbing (Cloudflare, AWS Shield, etc.) and cannot
be built in application code. This project defends the L7 (application)
layer only. See `DOCS/LIMITATIONS.md`.
