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
