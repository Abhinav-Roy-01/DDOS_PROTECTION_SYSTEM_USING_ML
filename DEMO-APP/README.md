# DEMO-APP

**Phase: 2**

The real target this project protects — a login or contact form with
JavaScript telemetry (mouse movement, click timing, keystroke patterns)
matching the 8-feature schema the ML model already expects:

```
click_count, avg_click_interval, click_interval_variance,
click_interval_entropy, mouse_velocity_variance,
max_element_click_rate, scroll_events, keystroke_count
```

## Implemented flow

- `TEMPLATES/index.html` — the protected contact form
- `STATIC/tracker.js` — browser-only click, interval, pointer, scroll, and
  keystroke feature collection
- `DEMO_ROUTES.py` — `/predict` model routing and one-time-token protected
  `/contact` submission

The browser sends only the eight documented behavior features to `/predict`.
Contact fields are sent to `/contact` only after a pass token is issued. A
successful contact record contains no IP address or pass token.

## Why this needs to exist

The ML model can only score behavior it's given. Without a real form
collecting real telemetry, there's nothing genuine for it to evaluate —
everything before this phase runs on synthetic/simulated data only.
