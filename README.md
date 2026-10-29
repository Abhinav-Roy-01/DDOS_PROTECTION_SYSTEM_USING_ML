# DDOS-SHIELD

ML-based application-layer (L7) bot/DDoS behavioral detection system.
Rebuilt scaffold for a real, deployed, protected demo target — not just a
local simulation.

**Status:** Local prototype — the Flask API, Redis-backed rate limiting,
synthetic ML model, browser telemetry demo, protected contact flow, one-time
pass tokens, game CAPTCHA, allowlisted admin dashboard, and quality-gated
retraining workflow are implemented for the local prototype. Cloud
deployment and production identity/TLS integration remain in progress.

## What this project actually does (read this first)

DDoS attacks split into two categories:

1. **Volumetric (L3/L4)** — UDP/SYN floods, amplification attacks. These
   saturate network bandwidth before traffic ever reaches an application.
   **This project cannot stop these** — that requires network-level
   scrubbing (CDN, ISP, anycast). No application code can.
2. **Application-layer (L7)** — HTTP floods, scripted bots, credential
   stuffing. **This is what this project targets.**

See `DOCS/LIMITATIONS.md` for the full, honest scope statement — read it
before demoing this to anyone.

## Structure

| Folder | Purpose | Reused from old project? |
|---|---|---|
| `INFRA/` | nginx config, systemd units, deployment docs | No — new |
| `API/` | Flask app: server, ML engine, rate limiter, auth | Yes — hardened rebuild |
| `ML/` | Model, dataset, training/retraining code | Yes — as-is |
| `FEEDBACK/` | Feedback capture + retrain trigger | Yes — as-is |
| `CAPTCHA/` | Game CAPTCHA blueprint | Yes — hardened rebuild |
| `DEMO-APP/` | Real target endpoint (login/contact form) with JS telemetry | No — new |
| `DASHBOARD/` | Live stats dashboard | Yes — as-is |
| `LOAD-TESTING/` | Locust scripts for self-testing (attacker simulation) | No — new |
| `TESTS/` | pytest suite | Yes — extended |
| `SCRIPTS/RETRAIN/` | Cron-driven retrain scheduler | Yes — as-is |
| `DOCS/` | Roadmap, architecture, results, limitations | Mixed |

## Build order

See `ROADMAP.md` for the full 6-phase, 12-week plan. Short version:

```
Phase 0  Scaffold + architecture           (this commit)
Phase 1  Real deployment infra (nginx, Redis, gunicorn)
Phase 2  Real demo target + ML wiring
Phase 3  Security hardening
Phase 4  Retrain loop in production
Phase 5  Load testing + observability
Phase 6  Validation + documentation
```

The local demo is functional and uses a checked-in bootstrap model. Its
shape-sequence CAPTCHA is a prototype challenge, not a substitute for a
production anti-abuse provider. Remaining components are filled in one
phase at a time, keeping the main branch runnable and tested.

## Run the local stack

Requirements: Docker Desktop with Docker Compose. From the repository root,
copy `.env.example` to `.env` and set unique random values for
`ADMIN_API_KEY`, `PASS_TOKEN_SECRET`, and `FEEDBACK_HASH_KEY`. Generate a
value with:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Build the synthetic dataset and bootstrap the ML model once:

```powershell
python ML/TRAINING/BUILD_DATASET.py
python ML/TRAINING/RETRAIN.py --bootstrap
```

Start the app, nginx, and Redis:

```powershell
docker compose -f INFRA/DOCKER/COMPOSE.yml up --build
```

Open `http://127.0.0.1:8090/` for the protected-contact demo or
`http://127.0.0.1:8090/health` for the liveness check. Admin endpoints are available through
nginx; send the configured key in the `X-Admin-Key` header. Admin requests
are restricted by `ADMIN_IP_ALLOWLIST` (loopback by default) and use a
separate rate bucket. Local Compose additionally trusts its private Docker
bridge range because Docker Desktop forwards loopback traffic through that
gateway; the published app port remains bound to localhost. Replace that
range with exact admin networks outside local Compose. The Redis port
is not published to the host. `/dashboard` shows live local metrics and
provides dry-run/deploy retraining controls. Stop the local stack with Ctrl+C, then run
`docker compose -f INFRA/DOCKER/COMPOSE.yml down`.

This is a local prototype only; it is not the public production deployment.
See [INFRA/DEPLOY.md](INFRA/DEPLOY.md) for deployment status and owner-only
AWS and DNS steps.

## Quick links

- `ROADMAP.md` — full phase-by-phase plan with deliverables
- `ARCHITECTURE.md` — system diagram, request flow, component responsibilities
- `DOCS/LIMITATIONS.md` — honest scope: what this protects against, what it doesn't
- `DOCS/REUSE_MAP.md` — which old-project files map to which new location
