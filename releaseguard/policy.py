"""Pure decision rules: no cluster operations in this module."""
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class Evidence:
    changed: bool
    baseline_healthy: bool
    rollout_ready: bool
    candidate_ready: Optional[bool]
    dependency_healthy: Optional[bool]
    metrics_available: bool
    requests: float = 0
    error_rate: float = 0
    p95_seconds: float = 0
    counter_reset: bool = False


@dataclass(frozen=True)
class Decision:
    state: str
    rollback: bool
    reason: str


def decide(evidence, policy):
    e = evidence
    if not e.metrics_available or e.counter_reset or e.dependency_healthy is None or e.candidate_ready is None:
        return Decision("insufficient_evidence", False, "required telemetry is missing, reset, or inconclusive")
    if not e.dependency_healthy:
        if e.changed and (not e.rollout_ready or not e.candidate_ready):
            return Decision("mixed_failure", False, "both candidate readiness and external dependency are degraded")
        return Decision("degraded_external_dependency", False, "external dependency unhealthy; app rollback has no demonstrated benefit")
    readiness_failure = not e.rollout_ready or not e.candidate_ready
    if not readiness_failure and e.requests < policy["minimum_requests"]:
        return Decision("insufficient_evidence", False, "not enough observed requests")
    slo_failure = e.error_rate > policy["maximum_error_rate"] or e.p95_seconds > policy["maximum_p95_seconds"]
    if not readiness_failure and not slo_failure:
        return Decision("healthy", False, "availability and observed traffic meet policy")
    if not e.changed or not e.baseline_healthy:
        return Decision("unattributed_degradation", False, "no changed app revision with a verified healthy baseline")
    reason = "changed candidate fails readiness" if readiness_failure else "changed candidate violates observed release-health policy"
    return Decision("rollback_eligible", True, reason)


def report(evidence, decision):
    return {"evidence": asdict(evidence), "decision": asdict(decision)}
