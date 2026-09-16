# DDOS-SHIELD

ML-based application-layer (L7) bot/DDoS behavioral detection system.
Rebuilt scaffold for a real, deployed, protected demo target — not just a
local simulation.

**Status:** Phase 0 — scaffold + roadmap. No live code yet; being built
incrementally per PHASE, one folder at a time.

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

Each phase's files currently exist as stubs — a docstring/comment block
explaining what goes there and which phase builds it, nothing functional
yet. They get filled in one phase at a time.

## Quick links

- `ROADMAP.md` — full phase-by-phase plan with deliverables
- `ARCHITECTURE.md` — system diagram, request flow, component responsibilities
- `DOCS/LIMITATIONS.md` — honest scope: what this protects against, what it doesn't
- `DOCS/REUSE_MAP.md` — which old-project files map to which new location
