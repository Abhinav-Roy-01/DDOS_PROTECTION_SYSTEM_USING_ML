# Build Roadmap — 3 Months

Goal: a live, publicly reachable demo app that measurably protects itself
against (1) single/few-source HTTP floods, (2) scripted bots on a real
form, and (3) slow-connection (Slowloris-type) attacks — with before/after
proof. Large distributed volumetric botnets are explicitly out of scope
(see `DOCS/LIMITATIONS.md`) — that's a network-layer problem, not an
application-layer one.

---

## Phase 0 — Foundation (Week 1)

**Goal:** Clean scaffold, finalized architecture, no migration confusion later.

- [ ] Scaffold folder structure (this commit)
- [ ] VPS provisioned (Oracle Cloud free tier / DigitalOcean) + domain/subdomain pointed
- [ ] Architecture diagram finalized (`ARCHITECTURE.md`)
- [ ] Old-project reuse map finalized (`DOCS/REUSE_MAP.md`)

**Deliverable:** Repo scaffold on GitHub, VPS SSH access confirmed, docs written.

---

## Phase 1 — Real Deployment Infra (Weeks 2–3)

**Goal:** A baseline PROTECTED endpoint live, before any ML is involved.

- [ ] nginx reverse proxy: `limit_req` (per-IP rate limiting), `limit_conn`
      (connection caps for Slowloris defense), sane timeouts
- [ ] gunicorn serving Flask (`gunicorn -w 4`) instead of the dev server
- [ ] Redis installed; `rate_limiter.py` rebuilt to be Redis-backed so
      state is shared correctly across gunicorn workers
- [ ] systemd service units (auto-restart on crash)
- [ ] HTTPS via Let's Encrypt/Certbot

**Deliverable:** A live URL that survives a basic flood/Slowloris test
using only nginx + Redis rate limiting — no ML involved yet.

**Test:** Run `hey`/`locust` against your own server from Phase 5's
tooling (built early, used here first); confirm nginx + Redis reject
excess requests from a single source.

---

## Phase 2 — Real Target + ML Pipeline (Weeks 4–5)

**Goal:** Move off synthetic data onto real behavioral data.

- [ ] `DEMO-APP/`: a real login or contact form with JS telemetry
      (mouse movement, click timing, keystroke counts — matches the
      existing 8-feature schema in `ML/MODELS/`)
- [ ] Wire `/predict` to this real form
- [ ] Reuse `ML/MODELS/` (aethercept model + `THRESHOLDS.json`) as-is —
      already calibrated to 99.4% human-allowed / 73%+ bot-blocked
- [ ] Wire `FEEDBACK/FEEDBACK_STORE.py` + `ML/TRAINING/RETRAIN.py` to
      this real traffic

**Deliverable:** A real form that allows a human filling it out normally,
and CAPTCHAs/blocks a `curl`/script submitting it.

**Test:** Script a fake form submission with `curl` — confirm it's
flagged. Fill the form normally in a browser — confirm it's allowed.

---

## Phase 3 — Security Hardening (Weeks 6–7)

**Goal:** Close every "not production yet" gap before this is
internet-facing for real.

- [ ] All secrets (`CAPTCHA_SECRET_KEY`, admin key, etc.) in `.env`, no
      hardcoded dev fallbacks
- [ ] Cookies `secure=True`, HTTPS-only
- [ ] Per-IP cap on feedback rows in `FEEDBACK_STORE.py` (stop one IP
      from poisoning the retrain data)
- [ ] Admin routes (`/api/*`) restricted to your own IP at the nginx layer

**Deliverable:** No hardcoded secret or dev-only fallback reachable from
the public internet.

---

## Phase 4 — Retrain Loop in Production (Weeks 8–9)

**Goal:** The retrain loop (already built) running on real traffic.

- [ ] `SCRIPTS/RETRAIN/RETRAIN_SCHEDULER.py` on a systemd timer / cron,
      daily
- [ ] Verify hot-reload works (`/api/model/reload`) after a real deploy
- [ ] Monitor quality-gate logs (`retrain_log.jsonl`) — confirm it
      correctly rejects bad retrains, not just accepts good ones
- [ ] Let 1–2 weeks of real traffic accumulate before the first real
      retrain

**Deliverable:** At least one real retrain cycle driven by real feedback
(actual bans + actual CAPTCHA passes, not synthetic data).

---

## Phase 5 — Observability + Load Testing (Week 10)

**Goal:** Demonstrable, measured proof — not just "trust me."

- [ ] `LOAD-TESTING/`: Locust scripts — a normal-user simulation profile
      and a flood-attack simulation profile
- [ ] Persistent request/click logs (SQLite is enough at this scale —
      Postgres/Timescale is overkill for a solo demo project)
- [ ] Dashboard shows live stats: requests/sec, % blocked, CAPTCHA rate

**Deliverable:** Before/after load-test graphs — undefended vs. defended,
same traffic profile.

---

## Phase 6 — Final Validation + Docs (Weeks 11–12)

**Goal:** An interview-ready, honestly-documented package.

- [ ] Controlled self-test of all three in-scope attack types (flood,
      scripted bot, Slowloris) against your own deployed instance
- [ ] `DOCS/RESULTS.md` — actual numbers, graphs, before/after
- [ ] `DOCS/LIMITATIONS.md` finalized — explicit about what's out of
      scope (volumetric/distributed attacks) and why
- [ ] 5-minute demo script/recording

**Deliverable:** Complete, deployed, documented, honestly-scoped project.

---

## Notes

- Add 2–3 buffer days at the end of each phase — first-time VPS/nginx/
  Redis setup issues are normal and eat time.
- Every self-test (Phase 1, 5, 6) is run against **your own infrastructure
  only**. Never point load-testing tools at anything you don't own or have
  explicit permission to test.
