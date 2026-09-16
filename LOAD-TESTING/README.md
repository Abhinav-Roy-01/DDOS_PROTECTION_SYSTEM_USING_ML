# LOAD-TESTING

Locust-based self-testing tools — used to generate the before/after
numbers in DOCS/RESULTS.md.

**Run only against your own deployed instance.** Never point these
scripts at third-party infrastructure.

```
locust -f LOCUSTFILE.py --host https://your-demo-domain.example
```
