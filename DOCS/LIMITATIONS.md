# Limitations — read before demoing this to anyone

## What this project DOES protect against (in scope)

1. **Single/few-source HTTP floods** — one or a handful of IPs hammering
   an endpoint. Handled by nginx `limit_req` + Redis-backed rate limiting.
2. **Slowloris-type connection exhaustion** — many slow/incomplete
   connections held open. Handled by nginx `limit_conn` + timeouts.
3. **Scripted bots on a JS-tracked form** — a bot that doesn't execute
   JavaScript (curl, requests, basic scripts) submitting a form that
   expects behavioral telemetry (mouse movement, click timing, keystroke
   patterns). Handled by the ML behavioral model.

## What this project does NOT protect against (out of scope)

1. **Large distributed volumetric attacks** (real botnets, amplification
   attacks, Gbps/Tbps traffic). This is a network/bandwidth-layer
   problem — traffic saturates the pipe before it reaches this
   application at all. Solving this requires CDN/anycast/ISP-level
   scrubbing (Cloudflare, AWS Shield, etc.), not application code. No
   amount of ML or rate limiting at this layer changes that.
2. **Sophisticated bots that execute real JavaScript** (headless
   Chrome/Puppeteer driving real mouse/keyboard events). These can, in
   principle, mimic the exact telemetry the ML model looks for. This
   project raises the bar for attackers significantly but is not
   unbeatable by a well-resourced adversary.
3. **Distributed application-layer floods** (thousands of unique IPs
   each sending low, individually-legitimate-looking request rates).
   Per-IP rate limiting doesn't catch this by design. Would need
   fingerprinting/ASN-level heuristics beyond this project's scope.

## Why this scope, and why it's stated this honestly

Being upfront about this is what makes the project credible — "detects
and mitigates L7 bot/flood traffic as one layer in a defense-in-depth
DDoS strategy" is an accurate, defensible claim. "Stops DDoS attacks" is
not, and claiming it invites exactly the kind of question this document
answers.

In a real production stack, this system would sit as the LAST layer:

```
Internet → CDN/Cloudflare (L3/L4 scrubbing) → WAF/edge rate-limit → THIS PROJECT (L7 behavioral signal) → App
```
