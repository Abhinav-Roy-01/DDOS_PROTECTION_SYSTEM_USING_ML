# Reuse Map — old project → new scaffold

Legend: **COPY** = bring as-is. **REBUILD** = same idea, rebuilt for
production (Redis-backed, hardened, etc). **NEW** = doesn't exist yet.

| Old path (DDOS_PROTECTION_SYSTEM_USING_ML/HTTP-LAYER-SHIELD/...) | New path | Action | Phase |
|---|---|---|---|
| `ML/MODELS/aethercept_model.pkl` | `ML/MODELS/aethercept_model.pkl` | COPY | 2 |
| `ML/MODELS/aethercept_scaler.pkl` | `ML/MODELS/aethercept_scaler.pkl` | COPY | 2 |
| `ML/MODELS/THRESHOLDS.json` | `ML/MODELS/THRESHOLDS.json` | COPY | 2 |
| `ML/DATASET/training_data.csv` | `ML/DATASET/training_data.csv` | COPY | 2 |
| `ML/DATASET/human_only.csv` | `ML/DATASET/human_only.csv` | COPY | 2 |
| `ML/TRAINING/RETRAIN.py` | `ML/TRAINING/RETRAIN.py` | COPY (path constants may need a small update if folder depth changes) | 4 |
| `API/ml_engine.py` | `API/ML_ENGINE.py` | COPY (rename only) | 2 |
| `API/FEEDBACK_STORE.py` | `FEEDBACK/FEEDBACK_STORE.py` | COPY (moved out of API/ into its own folder) | 2 |
| `API/RETRAIN_RUNNER.py` | `FEEDBACK/RETRAIN_RUNNER.py` | COPY (moved) | 4 |
| `API/server.py` | `API/SERVER.py` | REBUILD — add Redis-backed rate limiting, remove dev-mode `app.run(debug=True)`, wire to `DEMO-APP/` instead of the old synthetic `/predict` caller | 1–3 |
| `API/rate_limiter.py` | `API/RATE_LIMITER.py` | REBUILD — in-memory dict → Redis so state is shared across gunicorn workers | 1 |
| `API/auth.py` | `API/AUTH.py` | REBUILD — remove hardcoded dev admin-key fallback | 3 |
| `API/attack_simulator.py` | `LOAD-TESTING/` (replaced by real Locust scripts) | REBUILD as proper load-testing tool, not an in-app toy simulator | 5 |
| `CAPTCHA/captcha_routes.py` | `CAPTCHA/CAPTCHA_ROUTES.py` | REBUILD — remove hardcoded secrets, `secure=True` cookies | 3 |
| `DASHBOARD/templates/`, `DASHBOARD/static/` | `DASHBOARD/TEMPLATES/`, `DASHBOARD/STATIC/` | COPY, minor tweaks for new stats | 5 |
| `TESTS/test_http_layer_shield.py` | `TESTS/TEST_HTTP_LAYER_SHIELD.py` | COPY, update for Redis-backed rate limiter | 1 |
| `TESTS/TEST_FEEDBACK_RETRAIN.py` | `TESTS/TEST_FEEDBACK_RETRAIN.py` | COPY, update import paths for new folder layout | 2 |
| — | `DEMO-APP/` | NEW — real form with JS telemetry | 2 |
| — | `INFRA/` | NEW — nginx, systemd, deploy docs | 1 |
| — | `LOAD-TESTING/` | NEW — Locust scripts | 5 |

## Things to double check while copying

- Every cross-file import (`import FEEDBACK_STORE as feedback_store`,
  etc.) needs its path re-verified once files move folders — `FEEDBACK/`
  is now a sibling of `API/`, not a subfolder of it, so `sys.path`
  insertions in `SERVER.py` and `CAPTCHA_ROUTES.py` need one extra
  `os.path.join(..., "..", "FEEDBACK")` hop.
- `RETRAIN.py`'s path constants (`DATASET_DIR`, `MODELS_DIR`, etc.) are
  relative to its own file location — recheck them against the new
  folder depth after moving.
