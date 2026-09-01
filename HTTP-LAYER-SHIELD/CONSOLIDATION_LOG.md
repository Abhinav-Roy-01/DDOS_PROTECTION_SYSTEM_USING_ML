# Consolidation log — HTTP-LAYER-SHIELD merge

This documents exactly how the uploaded prior codebase
(`DDOS_PROTECTION_SYSTEM_USING_MACHINE_LEARNING.zip`) was consolidated into
`HTTP-LAYER-SHIELD/`. The uploaded zip contained four overlapping copies of
the same system (`DDOS_CAPTCHA_SYSTEM`, `DDOS_MACHINE_BACKEND`,
`DDOS_MACHINE_FRONTEND`, `INTEGRATED_SYSTEM`) plus a `DEMO` folder and an
unrelated project. Nothing was silently dropped — every decision below is
traceable back to source.

## Why HTTP-LAYER-SHIELD is a new top-level folder, not merged into CORE/API/ML

The uploaded system operates at the **HTTP application layer** (Flask,
behavioral click/mouse/keystroke telemetry). DNS-SHIELD's `CORE`, `API`, and
`ML` folders operate at the **DNS protocol layer** (UDP:53, DoH, DoTLS,
domain-name features). These are two different, complementary defense
layers — one blocks malicious *domains*, the other blocks malicious
*behavior at the HTTP edge*. Merging their files into the same folders
would have silently overwritten unrelated logic. Keeping them as siblings
means both stacks can run side by side (see updated `docker-compose.yml`)
and reference each other explicitly instead of one clobbering the other.

## Source of truth: INTEGRATED_SYSTEM

`INTEGRATED_SYSTEM` was the most recent and most complete folder — it
already merged the CAPTCHA blueprint, the ML engine, and the rate limiter
into one working Flask app (`server.py`). Verified byte-identical
(md5sum) against its counterparts before treating it as canonical:

| File | Identical across | Verdict |
|---|---|---|
| `aethercept_model.pkl` | INTEGRATED_SYSTEM, DDOS_MACHINE_BACKEND, DDOS_MACHINE_FRONTEND, zip root | 1 canonical copy kept in `ML/MODELS/` |
| `aethercept_scaler.pkl` | same four locations | 1 canonical copy kept in `ML/MODELS/` |
| `training_data.csv` | DDOS_MACHINE_BACKEND, DDOS_MACHINE_FRONTEND | 1 canonical copy kept in `ML/DATASET/` |
| `human_only.csv` | DDOS_MACHINE_BACKEND, DDOS_MACHINE_FRONTEND | 1 canonical copy kept in `ML/DATASET/` |
| `captcha_routes.py` | INTEGRATED_SYSTEM, DDOS_CAPTCHA_SYSTEM | 1 canonical copy kept in `CAPTCHA/` |
| `ml_bridge.py` | INTEGRATED_SYSTEM, DDOS_CAPTCHA_SYSTEM | 1 canonical copy kept in `CAPTCHA/` |
| `templates/dashboard.html`, `static/css/dashboard.css`, `static/js/dashboard.js` | INTEGRATED_SYSTEM only (newer than DDOS_MACHINE_FRONTEND's plain `templates/index.html`) | Kept from INTEGRATED_SYSTEM |

## File-by-file mapping

| New location | Original path | Notes |
|---|---|---|
| `API/server.py` | `INTEGRATED_SYSTEM/server.py` | Flask app: rate-limit + ban check → CAPTCHA redirect → `/predict` routing (block / captcha / allow) |
| `API/ml_engine.py` | `INTEGRATED_SYSTEM/ml_engine.py` | IsolationForest inference wrapper, loads the two `.pkl` files |
| `API/rate_limiter.py` | `INTEGRATED_SYSTEM/rate_limiter.py` | In-memory sliding-window limiter, ban list, `/matrix` + `/stats` data |
| `API/requirements.txt` | `INTEGRATED_SYSTEM/requirements.txt` | flask, flask-cors, redis, scikit-learn, gunicorn |
| `CAPTCHA/captcha_routes.py` | `INTEGRATED_SYSTEM/captcha_routes.py` | Dino-run HMAC-signed game CAPTCHA blueprint |
| `CAPTCHA/ml_bridge.py` | `INTEGRATED_SYSTEM/ml_bridge.py` | Redis status checks: blocked / verified / pending / unknown |
| `CAPTCHA/templates/captcha_game.html` | `INTEGRATED_SYSTEM/templates/captcha_game.html` | Game UI served on challenge |
| `CAPTCHA/REDIS_SETUP.md` | `DDOS_CAPTCHA_SYSTEM/REDIS_SETUP.md` | Only existed here, not duplicated in INTEGRATED_SYSTEM |
| `CAPTCHA/run_captcha.bat` | `DDOS_CAPTCHA_SYSTEM/run_captcha.bat` | Windows launch script, only existed here |
| `DASHBOARD/templates/dashboard.html` | `INTEGRATED_SYSTEM/templates/dashboard.html` | Live stats dashboard |
| `DASHBOARD/static/css/dashboard.css` | `INTEGRATED_SYSTEM/static/css/dashboard.css` | |
| `DASHBOARD/static/js/dashboard.js` | `INTEGRATED_SYSTEM/static/js/dashboard.js` | |
| `ML/MODELS/aethercept_model.pkl` | `INTEGRATED_SYSTEM/aethercept_model.pkl` | Trained IsolationForest, 1.3MB, verified identical across 4 copies |
| `ML/MODELS/aethercept_scaler.pkl` | `INTEGRATED_SYSTEM/aethercept_scaler.pkl` | Verified identical across 4 copies |
| `ML/DATASET/training_data.csv` | `DDOS_MACHINE_BACKEND/training_data.csv` | Full labeled dataset, verified identical to FRONTEND copy |
| `ML/DATASET/human_only.csv` | `DDOS_MACHINE_BACKEND/human_only.csv` | Human-only subset, verified identical to FRONTEND copy |
| `ML/TRAINING/datasetgenerator.py` | `DDOS_MACHINE_BACKEND/datasetgenerator.py` | 188-line generator: 3750 human + 1000 bot sessions |
| `ML/TRAINING/generate_dataset_v2.py` | `DDOS_MACHINE_BACKEND/generate_dataset (1).py` | 213-line variant — kept alongside (not identical to datasetgenerator.py), renamed only to avoid an illegal filename (parenthesis + space); logic untouched |
| `ML/TRAINING/hj.py` | `DDOS_MACHINE_BACKEND/hj.py` | **Not a scratch file — a bug-fixed rewrite of `datasetgenerator.py`.** Diffed line-by-line; `hj.py` fixes three real defects present in `datasetgenerator.py`: (1) a missing comma between `'avg_click_interval'` and `'click_interval_variance'` in the `Features` list silently concatenates them into one bad key; (2) `np.random.uniform(0.1,1,5,n)` in `gen_casual_browser` passes 4 positional args where `uniform()` expects 3 — likely a mistyped `1.5`; (3) `if __name__ == "_main_"` uses single underscores, so the generator block **never executes** when the script is run directly. `hj.py` corrects all three and adds the docstring header + `SCRIPT_DIR`-relative output paths. **Recommendation: treat `hj.py` as the working version; `datasetgenerator.py` is kept only for provenance and should not be run as-is.** |
| `ML/TRAINING/botsimulator.py` | `DDOS_MACHINE_BACKEND/botsimulator.py` | Synthetic bot traffic generator for live testing |
| `ML/TRAINING/summary.txt` | `DDOS_MACHINE_BACKEND/summary.txt` | Original author's notes on the training run |
| `ML/NOTEBOOKS/analysis.ipynb` | `DDOS_MACHINE_BACKEND/analysis.ipynb` | |
| `ML/NOTEBOOKS/api.ipynb` | `DDOS_MACHINE_BACKEND/api.ipynb` | |
| `ML/NOTEBOOKS/model.ipynb` | `DDOS_MACHINE_BACKEND/model.ipynb` | |
| `ML/NOTEBOOKS/FeatureEngineering.ipynb` | `DDOS_MACHINE_FRONTEND/.../FeatureEngineering.ipynb` | Only existed in FRONTEND, not duplicated elsewhere |
| `ML/NOTEBOOKS/IsolationForest.ipynb` | `DDOS_MACHINE_FRONTEND/.../IsolationForest.ipynb` | Only existed in FRONTEND |
| `TESTS/attacker.py` | `INTEGRATED_SYSTEM/attacker.py` | Multi-threaded flood attack simulator against the shield |
| `TESTS/test_predictions.py` | `INTEGRATED_SYSTEM/test_predictions.py` | Sends known bot/human feature vectors to `/predict` |
| `TESTS/flask_target_app.py` | `DDOS_MACHINE_BACKEND/app.py` | Dummy target Flask app the shield protects in local demos |
| `DEMO/aethercept_api.py` | `DEMO/aethercept_api.py` | Standalone lightweight API demo, separate from the main shield |
| `DEMO/aethercept_demo.html` | `DEMO/aethercept_demo.html` | Matching demo front-end |
| `DOCS/PRIOR_SYSTEM_README.md` | `DDOS_MACHINE_FRONTEND/.../README.md` | Original project README, preserved verbatim |
| `DOCS/PRIOR_SYSTEM_OVERVIEW.html` | zip root `README.html` | Original HTML overview doc, preserved verbatim |
| `DOCS/Eclipse6.0 PPT.pptx` | `DDOS_MACHINE_FRONTEND/.../Eclipse6.0 PPT.pptx` | Original hackathon presentation deck |

## Excluded from the merge (with reasons)

| Item | Reason |
|---|---|
| `DDOS_MACHINE_BACKEND/ngrok_recovery_codes.txt` | Live credential/recovery material — never bring secrets into a shared repo. Regenerate your own ngrok token instead; see `.env.example` for where it plugs in. |
| `.venv/` folders (3 copies), `.git/` history, `node_modules/` | Environment/build artifacts, not source — regenerated by `bootstrap.sh` / `npm install` |
| `DDOS_MACHINE_FRONTEND/.../ddos_integrated.zip` | A nested zip of what appears to be an earlier snapshot of INTEGRATED_SYSTEM itself — superseded by the actual INTEGRATED_SYSTEM folder, not opened |
| `DDOS_MACHINE_SERVERBASE/` (entire folder: `edunexus/`, `matrix_dashboard/`, `backend/`, Supabase schema, Vercel/Render configs) | This is a **different project** — a student portal app ("EduNexus") with its own React frontend, Supabase backend, and deployment configs. It shares no code path with the DDoS/DNS shield and was not force-fitted in. If this was meant to be part of the security system (e.g. as a protected target app for demos), say so and it can be added under `TESTS/` or a new `DEMO-TARGETS/` folder. |
| Root-level loose `aethercept_model.pkl` / `aethercept_scaler.pkl` (zip root, outside any subfolder) | Verified identical (md5) to the canonical copy already kept — redundant |

## How this plugs into the DNS-layer system

- `docker-compose.yml` now runs `http-layer-shield` as its own service on
  port 8080, alongside the DNS-layer `api` (8000) and `dns-resolver` (53/443/853).
- `INFRA/NGINX/nginx.conf` routes `/shield` to the HTTP-layer service.
- `SCRIPTS/MIGRATE/001_initial_schema.sql` adds an `http_shield_requests`
  hypertable so both layers' logs land in the same TimescaleDB instance.
- The two ML models are intentionally separate: the DNS-layer model
  (`ML/MODELS/dns_model.pkl`, not yet trained) scores **domain names**;
  the HTTP-layer model (`HTTP-LAYER-SHIELD/ML/MODELS/aethercept_model.pkl`,
  already trained) scores **browser behavior**. A request can be flagged
  by either or both.

## Recommended next step

Confirm whether `hj.py` and the `DDOS_MACHINE_SERVERBASE` folder should be
kept, repurposed, or deleted — everything else above is final and wired in.
