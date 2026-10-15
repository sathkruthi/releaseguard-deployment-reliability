# Engineering review — 2026-10-15

This is a single-agent source and execution review, not an independent collaborator approval. No numerical hiring score is assigned.

| Severity | Finding | Resolution and evidence |
|---|---|---|
| High | A remote `DOCKER_HOST` can override the apparent local Docker context. | Reject non-Unix overrides before any command; executable test in `test_docker_environment.py`. |
| High | YAML non-finite thresholds can bypass numeric comparisons. | Reject non-finite floats after schema validation; regression in `test_config.py`. |
| High | Successful Helm execution alone does not prove healthy recovery; timeout can follow a partial mutation. | Separate recovery observation and uncertain completion state; both tested in `test_controller.py`. |
| Medium | Aggregate counter growth can hide one instance resetting. | Compare per-instance series and reject resets or membership changes; tested in `test_metrics.py`. |
| Medium | Dependency rollout completion preceded two real failed app requests. | Preserve the failed observation, bound repeated fresh recovery windows, and fail if none is healthy. Real initial and corrected run evidence retained. |
| Medium | Default multi-platform image export referenced unavailable foreign-platform layers. | Native-platform archive export implemented and actually rerun through `scripts/images.py`. |
| Low | A same-name cluster could be unrelated or recreated. | Require a matching owner-controlled container-ID record; guard test rejects replacement identity. |

## Architecture and correctness

Small modules isolate pure configuration and decision logic from CLI commands. Rollback eligibility is deliberately narrower than unhealthy status. A baseline ties measured health to deployment UID, Helm revision, cluster ownership and supported manifest fingerprint. Immediately before rollback, the target is revalidated. Counter windows are per-instance and per-revision; insufficient or mixed evidence fails conservatively.

The local baseline is trusted owner input. It is not signed, freshness-expiring, or protected against a hostile user who can edit the project/Docker socket. Concurrent operators can race checks and mutations; no distributed lock is implemented. Scope is one owner operating a fixed local demonstration.

## Security and reliability

Loopback NodePort mappings, explicit kubeconfig, namespace restrictions, non-root/read-only application containers, dropped capabilities, disabled app service-account token, bounded CPU/memory, and command/request timeouts reduce accidental exposure. Original code is unlicensed; third-party notices are preserved. Dependency scans are point-in-time, not a permanent security guarantee. Secret scans cover tracked content and genuine Git history; ignored credentials are excluded from publication and CI artifacts.

Manifest validation covers the documented sample fields; it is not a complete Kubernetes admission controller. Infrastructure bootstrap trusts this repository's fixed local manifests and does not apply the sample's full semantic policy to Prometheus. Docker privileges and Kubernetes client credentials inherently permit more than the app scope; the guard is a safety check, not operating-system isolation.

## Tests and documentation

Behavioral unit tests cover policy boundaries, malformed schema shapes, safe target identity, resource constraints, reset handling, rejection before upgrade, and uncertain recovery. Real kind integration covers rollout/readiness, measured latency, external dependency attribution and drift. The Go sample has no isolated handler unit coverage; integration is its principal behavioral verification. Coverage and actual local commands are preserved, with no invented percentages or performance claims.

Remaining limitations are explicit in the README and design. A fresh private GitHub Actions run is required before the repository is offered for public approval. Any CI-specific failure will be recorded and fixed before completion.
