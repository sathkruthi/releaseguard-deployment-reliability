import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from releaseguard.cluster import CommandError
from releaseguard.config import fingerprint, load_config
from releaseguard.controller import Controller, app_manifest


class RecoveryTests(unittest.TestCase):
    def setup_controller(self):
        cluster = Mock()
        cluster.config = load_config("configs/local.yaml")
        manifest = Path("tests/fixtures/valid.yaml").read_text()
        deployment = app_manifest(manifest)
        cluster.render.return_value = manifest
        cluster.deployment.return_value = deployment
        cluster.rollout.return_value = True
        controller = Controller(cluster)
        controller.valid_baseline = Mock(return_value=(True, None))
        controller.measure = Mock(
            side_effect=[
                {"decision": {"state": "rollback_eligible", "rollback": True}},
                {"decision": {"state": "insufficient_evidence", "rollback": False}},
            ]
        )
        return (
            cluster,
            controller,
            {"fingerprint": fingerprint(deployment), "helm_revision": 1},
        )

    def test_command_success_does_not_prove_recovery(self):
        cluster, controller, baseline = self.setup_controller()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(json.dumps(baseline))
            result = controller.deploy("v2", path)
        if os.getenv("RG_UNSAFE_RECOVERY") == "1":
            # Isolated anti-example: declaring success from a completed command alone.
            result["state"] = "recovered" if result["rollback_performed"] else "failed"
        self.assertEqual(result["state"], "recovery_unverified")
        self.assertTrue(result["rollback_performed"])
        cluster.rollback.assert_called_once_with(1)

    def test_failed_rollback_is_reported_as_uncertain(self):
        cluster, controller, baseline = self.setup_controller()
        cluster.rollback.side_effect = CommandError("wait timed out after possible patch")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(json.dumps(baseline))
            result = controller.deploy("v2", path)
        self.assertEqual(result["state"], "recovery_unverified")
        self.assertTrue(result["rollback_attempted"])
        self.assertIsNone(result["rollback_performed"])
