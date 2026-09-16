"""
LOCUSTFILE.PY -- self-testing load generator.

PHASE: 1 (basic flood profile, used to validate nginx+Redis) -> 5 (full
          normal-vs-attack comparison profiles)

NOTE ON THE FILENAME: Locust's CLI auto-discovers a file named
"locustfile.py" (lowercase) by default. Since this project's convention
is ALL CAPS, run it explicitly with the -f flag instead of relying on
auto-discovery:
    locust -f LOCUSTFILE.py

WHAT GOES HERE:
    - NormalUser class -- simulates realistic human traffic (reasonable
      request intervals, follows the actual DEMO-APP flow)
    - FloodAttacker class -- simulates a single/few-source HTTP flood
      (used in Phase 1 and Phase 6 to prove nginx+Redis rate limiting works)
    - Both run against YOUR OWN deployed instance only -- never point
      this at infrastructure you don't own or have explicit permission
      to test.

NOT YET IMPLEMENTED.
"""
