# Tests and reproducibility

`make test lint audit` runs Python behavioral tests, Go race/build/vet checks, formatting/static checks, and a live Python dependency advisory audit. The Go sample currently has no isolated unit tests; the real kind suite exercises its HTTP and metrics behavior. Do not interpret `go test` as sample-handler coverage.

`PYTHONPATH=. .venv/bin/python scripts/regressions.py` runs isolated unsafe policy variants and expects each to fail its acceptance test, then runs the corrected policy and expects a pass. These are explicit test-only anti-examples; the runtime CLI has no unsafe-mode switch. They are not purported historical production bugs.

`make integration` verifies actual kind, Helm, Kubernetes and Prometheus behavior, including a broken rollout, verified rollback, external dependency outage without rollback, recovery, latency failure, and live replica drift. The harness restores the dependency and replica changes in `finally` blocks. Reports include actual observations; it does not replace missing evidence with expected values. It fails if any acceptance assertion fails.

Coverage from Python unit tests is reported separately from integration evidence. Unit coverage does not exercise all command adapters or network operations. A fresh GitHub Actions runner repeats the complete setup and integration; artifacts contain only selected sanitized JSON/text reports, never kubeconfig or ownership credentials.

The original failed integration run is retained: dependency rollout completion preceded two failed app requests. The correction was bounded repeated recovery observation, preserving unsuccessful attempts rather than claiming immediate health. This demonstrates why recovery is a separate state.
