# INCIDENT-003 — External dependency outage is not a release regression

**Controlled local fault.** Set `DEPENDENCY_FAIL=1` on the separate dependency deployment. The app stays ready and keeps its original template, but real `/work` requests return 503.

A test-only blanket rollback rule fails the acceptance test. The corrected policy independently checks dependency health and reports `degraded_external_dependency`. The live integration asserts that the app template and Helm revision remain unchanged. Rolling back the app would not repair the separate failed deployment.

Reproduce: `make incident ID=003`; inspect `evidence/incident003.json` and the unsafe/corrected test logs under `evidence/regressions/`.

Acceptance: more than 90% observed work failures, unhealthy dependency, unchanged app template, no Helm revision change, and no app rollback. Restore the dependency and require a fresh healthy window.

The first real restoration observation still contained two 503 responses during service convergence. It was correctly classified as degraded, not recovered. See `evidence/dependency-restoration-first-observation.json` and `initial-integration-run.txt`. The harness now preserves up to three bounded recovery observations; it never treats deployment completion alone as recovery.
