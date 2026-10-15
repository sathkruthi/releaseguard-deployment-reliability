import os
import unittest
from dataclasses import replace

from releaseguard.policy import Evidence, decide

POLICY = {
    "minimum_requests": 20,
    "maximum_error_rate": 0.05,
    "maximum_p95_seconds": 0.5,
}
GOOD = Evidence(True, True, True, True, True, True, 40, 0, 0.1)


class DecisionTests(unittest.TestCase):
    def test_health_and_sample_boundary(self):
        self.assertEqual(decide(GOOD, POLICY).state, "healthy")
        self.assertEqual(decide(replace(GOOD, requests=19), POLICY).state, "insufficient_evidence")

    def test_readiness_and_slo_regressions(self):
        for e in [
            replace(GOOD, rollout_ready=False, candidate_ready=False, requests=0),
            replace(GOOD, error_rate=0.5),
            replace(GOOD, p95_seconds=1),
        ]:
            self.assertTrue(decide(e, POLICY).rollback)

    def test_missing_and_mixed_evidence(self):
        for e in [
            replace(GOOD, metrics_available=False),
            replace(GOOD, counter_reset=True),
            replace(GOOD, dependency_healthy=None),
            replace(GOOD, candidate_ready=None),
            replace(GOOD, dependency_healthy=False, candidate_ready=False),
        ]:
            self.assertFalse(decide(e, POLICY).rollback)

    def test_incident003_dependency_does_not_rollback(self):
        e = replace(GOOD, changed=False, dependency_healthy=False, error_rate=1)
        decision = decide(e, POLICY)
        unsafe = os.getenv("RG_UNSAFE_ROLLBACK") == "1"
        rollback = e.error_rate > POLICY["maximum_error_rate"] if unsafe else decision.rollback
        self.assertFalse(rollback, "dependency outage incorrectly triggered app rollback")
        self.assertEqual(decision.state, "degraded_external_dependency")

    def test_no_baseline_or_revision_cannot_authorize_rollback(self):
        for e in [
            replace(GOOD, changed=False, error_rate=1),
            replace(GOOD, baseline_healthy=False, error_rate=1),
        ]:
            self.assertFalse(decide(e, POLICY).rollback)


if __name__ == "__main__":
    unittest.main()
