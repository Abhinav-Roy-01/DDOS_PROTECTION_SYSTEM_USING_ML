# DASHBOARD

## Implemented

- Open `/dashboard` from the local application.
- Enter the configured admin key; the browser keeps it in tab-scoped
  `sessionStorage`.
- The page polls protected API endpoints for model/feedback counters, score
  histogram, request history, bans, and verified contact messages.
- Allowlisted admin source addresses and the `X-Admin-Key` header are both
  required to access the data APIs.

The dashboard is a local prototype. It is not a substitute for production
identity management, TLS, or a hardened administrator network.
