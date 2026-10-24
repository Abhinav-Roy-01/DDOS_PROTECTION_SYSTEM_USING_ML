# Build Roadmap: 16 weeks (26 Oct 2026 to 14 Feb 2027)

Goal: a live, protected demo app with a frontend, plus a research paper on
three angles: (1) feedback-loop poisoning, (2) adversarial evasion,
(3) calibration + detector comparison. Assumes ~10-12 hours per week.
Large distributed volumetric attacks are out of scope (see DOCS/LIMITATIONS.md).

| Week (start) | BUILD | FRONTEND | RESEARCH |
|---|---|---|---|
| W1 (26 Oct) | NGINX.CONF.EXAMPLE, laptop checks | | Literature search, lock research questions |
| W2 (2 Nov) | AWS Lightsail deploy, HTTPS, domain + Cloudflare, Locust flood baseline | | Threat models, experiment design |
| W3 (9 Nov) | ML_ENGINE, /predict, thresholds, FEEDBACK_STORE wiring | | |
| W4 (16 Nov) | CAPTCHA_ROUTES (hardened) | DEMO-APP: form + JS telemetry | |
| W5 (23 Nov) | Hardening: secrets, cookies, per-IP feedback cap, origin lock | DASHBOARD v1 | |
| W6 (30 Nov) | Retrain loop in production | Frontend fixes | RESEARCH/ folder, bot suite v1, consent notice, human data collection starts |
| W7 (7 Dec) | | | Data collection + detector comparison code |
| W8 (14 Dec) | | | Angle 3 runs: ablation, calibration curves; data collection ends |
| W9 (21 Dec) | Buffer | | Angle 3 analysis and figures |
| W10 (28 Dec) | | | Angle 1: poisoning simulator + experiments |
| W11 (4 Jan) | | | Angle 1 analysis; Angle 2 adversarial bot generators |
| W12 (11 Jan) | | | Angle 2 experiments + defense re-evaluation |
| W13 (18 Jan) | System evaluation on AWS, persistent logs | Dashboard polish | Paper: methods |
| W14 (25 Jan) | RESULTS.md, LIMITATIONS.md | | Paper: results + related work |
| W15 (1 Feb) | Demo script/video, README final | | Paper full draft + figures |
| W16 (8 Feb) | Buffer | | Paper revision, submission-ready |

## Milestones
- W2 end: live AWS endpoint surviving floods with nginx + Redis only.
- W6 end: working prototype (DEMO-APP + DASHBOARD + ML + CAPTCHA + retrain loop).
- W13 end: measured before/after numbers.
- W16 end: paper draft ready.

## Notes
- Every load test runs against your own infrastructure only.
- Human data: consent notice, aggregate features only (no raw IPs).