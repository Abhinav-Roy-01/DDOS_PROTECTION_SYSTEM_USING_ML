# Decisions

## Local development stack

- The local Compose stack binds nginx only to `127.0.0.1:8090`; Redis is
  reachable only on the private Compose network. This avoids exposing the
  development services to the LAN and avoids conflicts with host ports.
- The local stack includes a dedicated nginx config because the production
  nginx example targets a host-installed gunicorn process, while Compose
  services resolve each other by service name.
- The local API process uses one gunicorn worker. Production worker settings
  remain defined by the deployment requirements.

## PRD schedule

The supplied PRD refers to a Section 13 weekly plan, but the supplied
document ends at Section 12.4. The repository roadmap currently contains a
16-week schedule. Work remains incremental and will not skip ahead to later
features; confirm the intended sequence with the owner if the missing PRD
section changes it.

## ML feature units

- The historical browser tracker reports entropy in bits and computes
  max-element click share. The PRD requires entropy in nats and
  max-element clicks per second; the historical synthetic data already uses
  per-second rates but expresses entropy in bits.
- The owner selected the PRD contract. Synthetic entropy is converted from
  bits to nats by multiplying by `ln(2)`, and live telemetry must calculate
  the maximum per-element clicks per second. The historical human fixture's
  entropy therefore converts from `2.304229902307089` bits to nats.
