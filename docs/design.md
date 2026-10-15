# ReleaseGuard design

Status: pre-implementation design. No implementation or verification is claimed yet.

## Problem and minimum complete release

Validate deployment configuration, inspect real Kubernetes rollouts, distinguish revision regressions from dependency outages, and execute a verified rollback only when evidence supports it. Use a dedicated local kind cluster, Helm sample application, Prometheus, synthetic traffic, and JSON incident reports. No cloud costs, customer data, remote clusters, or production deployment claims.

## Architecture

Python CLI → schema/semantic validator → guarded kubectl/Helm adapter → dedicated kind cluster. A Go sample application exposes readiness, work, and actual Prometheus request/latency metrics. A separate dependency deployment supplies a real network dependency. Prometheus scrapes each application pod through headless DNS discovery, including unready pods for diagnosis.

The app and dependency are separate deployments; rolling back the app does not modify its dependency. NodePorts map only to host loopback through explicitly configured kind port mappings. No background port-forward process is required.

## Configuration and contracts

JSON and YAML share one strict schema. Required: environment, exact local context, namespace/release, approved local URLs, rollout deadline, observation duration, minimum samples, maximum error rate, and latency threshold. Unknown properties and invalid numeric types/bounds are rejected before a command can mutate the cluster.

Manifest inspection checks deployment identity, replica bounds, image policy, non-root/read-only security settings, CPU/memory requests and limits, HTTP probes, and prohibited host access. Production-profile validation requires at least two replicas and image digests; it is a policy exercise on local data, never authorization for a remote deployment.

Helm renders the sample before deployment. Drift detection compares explicitly supported desired fields against the live deployment, including replicas, image, resources, environment, and probes. Report each differing path precisely; do not claim complete Kubernetes-object semantic equivalence.

## Local authorization boundary

Every mutation uses an explicit kubeconfig, context and namespace. Before use, verify: Docker context is a local Unix socket; kind lists the exact `releaseguard` cluster; its control-plane container has matching kind labels; kubeconfig server is loopback and its port matches that container's Kubernetes API mapping. Reject remote endpoints, renamed unrelated contexts, mismatched containers, or arbitrary namespaces/releases. Do not change the user's global kubeconfig or current context.

Kubeconfig and local baseline/report state stay under ignored `.local/`; never commit credentials. Commands use argument arrays rather than shell interpolation. Rollback is restricted to this named local application release and a recorded known-good Helm revision whose stored manifest agrees with its baseline identity.

## Release states

`validated → baseline_verified → deploying → observing → healthy`.

Failures become `rejected_configuration`, `degraded_external_dependency`, `mixed_failure`, `insufficient_evidence`, or `rollback_eligible`. Only `rollback_eligible` may transition to `rolling_back → verifying_recovery → recovered` or `recovery_unverified`. Persist machine-readable evidence for every terminal outcome. Never label a rollback successful merely because Helm returned zero.

## Baseline, health, and telemetry

Record a baseline only after Kubernetes availability and an actual traffic observation satisfy policy. Store cluster/release/deployment identity, current Helm revision, image, supported template fingerprint, health evidence, and timestamp. A local file is an owner-controlled demonstration record, not a signed production attestation.

Prometheus supplies cumulative request counters and latency buckets by application revision. Capture before/after snapshots around generated traffic, calculate nonnegative deltas, error fraction, and bucket-based p95. Require enough observed requests, a successful scrape, and candidate revision identity. Missing metrics, counter resets, absent revision samples, or inconclusive dependency checks block automatic rollback. Bucket p95 is an estimate, not an exact percentile.

Readiness failure can supply rollout evidence even when no live traffic reaches the candidate: the existing healthy pod remains available with zero max-unavailable. Require candidate metrics plus known-good baseline, changed template, and a healthy independent dependency before attributing rollback eligibility to a revision.

## Rollback eligibility

Eligible only when a valid known-good baseline exists, the app revision changed, the dependency is independently healthy, required telemetry is available, and either the new rollout fails readiness or sufficient traffic violates an error/latency threshold. Unknown or mixed evidence is not eligible. No app revision change means no evidence that rolling back would improve a new regression.

Rollback targets the recorded Helm revision after verifying its stored manifest. Observe actual restored image/template and Kubernetes availability, then collect a fresh traffic window for recovery verification. Old failing counters must not contaminate the recovery window. A successful command without healthy observed recovery remains unverified.

## Failure modes and recovery

Kubernetes/Helm timeouts are bounded. Report command failure without treating missing state as health. An external dependency outage leaves the application revision unchanged and must not trigger an app rollback. Simultaneous dependency and revision failures produce a mixed diagnosis. Partial rollback or missing post-rollback telemetry requires operator investigation. Repeated CLI runs do not assume an earlier baseline is still valid.

## Security and resource constraints

Loopback-only local exposure, synthetic fixtures, bounded requests/timeouts, non-root containers, read-only filesystem, dropped Linux capabilities, explicit resources and read-only CI permissions. Keep one local Kubernetes node and small workloads within the 16 GB workstation. Stop only earlier named portfolio stacks if resource pressure requires it; preserve their data.

## Testing and incidents

Unit tests: schema and semantic failures, environment-specific policy, drift projections, decision matrix including mixed/missing evidence, counter resets and histogram quantiles, local-context guard rejection, and argument construction. Integration: real kind cluster, Helm deployment, live Prometheus data, actual faulty image rollout, controlled rollback and verified recovery, unchanged-revision dependency outage, and drift detection.

Incident 001: syntactically valid unsafe production-profile configuration is rejected with exact policy paths before deployment. Incident 002: a defective sample image fails readiness; the guarded controller diagnoses, rolls back to a measured baseline, and verifies recovery. Incident 003: a real dependency outage degrades requests with no app template change; the controller attributes the dependency and performs no rollback. Restore the dependency and verify recovery.

Each incident preserves problem, reproduction, real evidence, root cause, executable acceptance criteria, and genuine corrective commits. Isolated unsafe decision policies demonstrate false rollback or unsafe acceptance only in tests; they are never default runtime behavior.

## Acceptance criteria

1. Fresh documented setup creates only the dedicated local cluster and deploys the real sample.
2. JSON/YAML, schema, semantic and environment policy checks reject unsafe releases precisely.
3. Desired-versus-live drift is detected for the documented fields.
4. Real failed candidate rollout is detected and safely rolled back only with sufficient evidence.
5. Recovery requires restored availability and fresh observed health, not just command success.
6. External dependency outage with unchanged app revision produces no rollback.
7. Missing, reset, mixed, or insufficient telemetry blocks automatic destructive guesses.
8. Every mutation refuses non-local or mismatched cluster targets.
9. Unit/static/dependency/secret checks and real kind scenarios pass with captured output.
10. Private GitHub CI and publication review precede separate public-publication approval.

## Known limits and trade-offs

One node and one sample app; no multi-cluster orchestration, production credentials, canary traffic routing, persistent telemetry storage, automated baseline attestation, or universally complete drift comparison. Synthetic workloads and deterministic defects are engineering exercises, not historical incidents. Reconcile thresholds to the observed local environment; finite tests do not certify all Kubernetes failures. Correctness gates take priority over the deadline.
