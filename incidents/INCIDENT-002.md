# INCIDENT-002 — Defective revision and verified rollback

**A real local Kubernetes failure using a deliberately defective sample build.** Revision v2 returns 503 from readiness. The rolling strategy leaves v1 serving, so a simple service health check alone could miss the candidate's failure.

ReleaseGuard observes failed Kubernetes rollout and v2's readiness metric through unready-pod scraping. With a measured v1 baseline and a healthy independent dependency, it classifies the changed candidate as rollback-eligible. Helm restores the recorded revision; ReleaseGuard then compares the restored supported template, checks rollout readiness, and measures a fresh healthy traffic window.

Reproduce: `make demo`, then `.venv/bin/python -m releaseguard --report .local/v2.json deploy --image v2`, or `make incident ID=002`. Inspect `evidence/incident002.json` for the actual failed candidate and recovery windows.

Acceptance: candidate readiness is false, rollback is justified, the recorded baseline template is restored, and only fresh healthy observations permit `recovered`. `tests/test_controller.py` proves that a successful rollback command with missing recovery evidence remains `recovery_unverified`; a command timeout leaves completion uncertain. Missing telemetry never authorizes a guessed rollback.

An additional real v3 build remains ready but sleeps 700 ms per work request. `evidence/latency-regression.json` demonstrates the separate latency-based rollback path. Histogram p95 is a bucket bound, not exact request timing.

The test-only command-success anti-example is reproduced by `scripts/regressions.py`; it must fail the same recovery acceptance assertion. See `evidence/regressions/002-unsafe.txt` and `002-corrected.txt`. No unsafe flag exists in the runtime CLI.
