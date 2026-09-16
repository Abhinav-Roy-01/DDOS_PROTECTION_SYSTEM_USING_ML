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

## What goes here

- `TEMPLATES/` — the actual form HTML
- `STATIC/` — JS telemetry collector (mouse/click/keystroke tracking),
  submits collected features alongside the form data to `/predict`

## Why this needs to exist

The ML model can only score behavior it's given. Without a real form
collecting real telemetry, there's nothing genuine for it to evaluate —
everything before this phase runs on synthetic/simulated data only.

NOT YET IMPLEMENTED.
