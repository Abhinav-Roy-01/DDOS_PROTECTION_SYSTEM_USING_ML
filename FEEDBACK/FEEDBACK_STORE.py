"""
FEEDBACK_STORE.PY -- turns live outcomes (bans, CAPTCHA passes) into
labeled training rows.

PHASE: 2 (wired to real DEMO-APP traffic) -> 3 (add per-IP cap, hardening)
REUSE: copy as-is from old project's API/FEEDBACK_STORE.py, moved to its
       own top-level FEEDBACK/ folder -- see DOCS/REUSE_MAP.md. Update the
       sys.path insert in SERVER.py / CAPTCHA_ROUTES.py to point one level
       up to this new location.

WHAT GOES HERE:
    - record_pending(ip, features)      -- called on every /predict
    - label_as_bot(ip) / label_as_human(ip) -- called on ban / CAPTCHA pass
    - pending_count(), feedback_counts()
    - Phase 3 addition: per-IP cap on rows contributed per retrain window,
      to prevent a single actor from poisoning the training data

NOT YET IMPLEMENTED.
"""
