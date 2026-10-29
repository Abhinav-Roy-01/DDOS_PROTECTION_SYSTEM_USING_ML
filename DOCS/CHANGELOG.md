# Changelog

## Unreleased

- Added a local Docker Compose stack for the Flask API, nginx, and Redis.
- Updated the local environment template and setup instructions.
- Recorded the local-stack decisions and the missing PRD schedule section.
- Added a deterministic synthetic dataset builder with entropy converted to
  the PRD's nats unit and exact dependency pins for reproducible training.
- Added model validation, integrity-checked artifact loading, threshold
  routing, bootstrap training, and synthetic baseline metrics.
