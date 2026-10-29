# Changelog

## Unreleased

- Added a local Docker Compose stack for the Flask API, nginx, and Redis.
- Updated the local environment template and setup instructions.
- Recorded the local-stack decisions and the missing PRD schedule section.
- Added a deterministic synthetic dataset builder with entropy converted to
  the PRD's nats unit and exact dependency pins for reproducible training.
- Added model validation, integrity-checked artifact loading, threshold
  routing, bootstrap training, and synthetic baseline metrics.
- Added IP-bound single-use pass tokens with Redis replay protection.
- Added Redis-backed feedback labels with hashed IPs, per-IP/subnet caps,
  audit records, and recoverable training exports.
- Added the ML-backed `/predict` flow, protected contact form, browser
  telemetry, rolling prediction budget, and score/counter/message storage.
- Added a short-lived shape-sequence CAPTCHA that records only successful
  challenged samples as human feedback and issues a one-time pass token.
- Added admin source-IP allowlisting, a separate admin rate bucket, request
  IDs/security headers, readiness reporting, and the live dashboard.
- Added human-canary quality gates, retraining rollback/backup handling,
  shared Redis job locking, admin status endpoints, and a scheduler client.
- Calibrated the bootstrap model's hard-block boundary so the observed
  long-gap human browser sample is challenged instead of immediately blocked.
