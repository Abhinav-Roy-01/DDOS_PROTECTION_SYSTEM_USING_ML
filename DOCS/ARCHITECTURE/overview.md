# DNS Shield — architecture overview

## Two defense layers, one system

This project now merges two complementary layers:

1. **DNS protocol layer** (`CORE/`, `API/`, `ML/`, `THREAT-INTEL/`,
   `PASSIVE-ANALYSIS/`) — new, being built for SIH. Filters malicious
   *domains* at the resolver level (UDP:53, DoH, DoTLS) before a
   connection is ever made.
2. **HTTP application layer** (`HTTP-LAYER-SHIELD/`) — a prior working
   system, merged in. Filters malicious *behavior* at the web-app edge
   using mouse/click/keystroke telemetry, an IsolationForest bot
   classifier, a Dino-run CAPTCHA challenge, and IP-based rate limiting.

See `HTTP-LAYER-SHIELD/CONSOLIDATION_LOG.md` for the full file-by-file
merge history and what was deliberately excluded.

## System layers

1. CORE — DNS protocol layer (UDP, DoH, DoTLS)
2. ML — DNS-layer anomaly detection (DGA, tunnelling) — not yet trained
3. THREAT-INTEL — Blacklists, STIX/TAXII, reputation
4. PASSIVE-ANALYSIS — PCAP and Zeek offline processing
5. API — FastAPI REST interface (DNS layer)
6. HTTP-LAYER-SHIELD — Flask behavioral shield (HTTP layer, merged, trained model included)
7. DASHBOARD — React monitoring interface (DNS layer)
8. INFRA — Docker, K8s, Nginx, Prometheus, Grafana (both layers)

## DNS query lifecycle

Client query → DNS resolver → cache check → blacklist check →
ML scoring → threat intel lookup → allow/block → upstream forward/NXDOMAIN

## HTTP request lifecycle (HTTP-LAYER-SHIELD)

Client request → rate limiter + ban check → CAPTCHA-required check →
`/predict` with behavioral features → IsolationForest score:
- score < -0.15 → block + ban
- -0.15 to 0.10 → CAPTCHA challenge (Dino-run, HMAC-signed)
- score > 0.10 → allow (human)

## Why two separate ML models

| | DNS-layer model | HTTP-layer model |
|---|---|---|
| Location | `ML/MODELS/dns_model.pkl` (to be trained) | `HTTP-LAYER-SHIELD/ML/MODELS/aethercept_model.pkl` (trained) |
| Scores | Domain names (entropy, DGA patterns) | Browser behavior (click/mouse/keystroke) |
| Blocks | Malicious domain resolution | Bot traffic at the HTTP edge |
| Runs in | `dns-resolver`, `doh-server`, `api` containers | `http-layer-shield` container |

A request can be flagged by either layer independently — they don't share
a model, but they do share Redis and TimescaleDB for unified logging
(see `SCRIPTS/MIGRATE/001_initial_schema.sql`).
