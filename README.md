# DNS Shield

DNS Filtering Service using Threat Intelligence and ML — SIH problem
statement, organizational-grade implementation.

This project now merges **two defense layers**:

1. **DNS protocol layer** — new build in progress (`CORE/`, `API/`, `ML/`,
   `THREAT-INTEL/`, `PASSIVE-ANALYSIS/`). Filters malicious domains at the
   resolver before a connection is made.
2. **HTTP application layer** (`HTTP-LAYER-SHIELD/`) — a working prior
   system, merged in wholesale. Filters malicious behavior at the web-app
   edge using a trained IsolationForest model, Redis-backed rate limiting,
   and a Dino-run CAPTCHA challenge.

See `HTTP-LAYER-SHIELD/CONSOLIDATION_LOG.md` for the exact merge history —
every file's origin, every duplicate resolved, and everything intentionally
left out (with reasons).

## Quick start — DNS layer (new build)
```bash
./SCRIPTS/SETUP/bootstrap.sh
make seed
make dev
```

## Quick start — HTTP layer (merged, already trained)
```bash
pip install -r HTTP-LAYER-SHIELD/API/requirements.txt
make shield          # starts the Flask shield on :8080
make shield-test      # sends known bot/human vectors to /predict
make shield-attack    # runs the flood attack simulator against it
```

## Run both together
```bash
docker-compose up
```
- DNS resolver → `:53` / `:443` (DoH) / `:853` (DoTLS)
- DNS-layer API → `:8000`
- HTTP-layer shield → `:8080`
- Dashboard → `:3001`
- Grafana → `:3000`

## Documentation
- Architecture: `DOCS/ARCHITECTURE/overview.md`
- API spec: `DOCS/API-SPEC/openapi.yaml`
- Merge history: `HTTP-LAYER-SHIELD/CONSOLIDATION_LOG.md`
