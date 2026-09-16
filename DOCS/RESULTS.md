# Results — filled in during Phase 6

This file will hold the actual before/after numbers once Phase 5/6
load-testing is complete. Placeholder structure below.

## Test 1 — HTTP flood (single source)

- Undefended baseline: TBD (requests/sec sustained, error rate, latency)
- Defended (nginx + Redis rate limit): TBD

## Test 2 — Slowloris (connection exhaustion)

- Undefended baseline: TBD (time to exhaust worker pool)
- Defended (nginx limit_conn + timeouts): TBD

## Test 3 — Scripted bot on DEMO-APP form

- Undefended baseline: TBD (bot submission success rate)
- Defended (ML behavioral scoring): TBD (detection rate, false-positive
  rate on real human submissions)

## Retrain loop — real-world cycle

- Date of first real retrain: TBD
- Feedback rows folded in (human / bot): TBD
- Threshold shift vs. seed values: TBD
- Quality gate outcome: TBD
