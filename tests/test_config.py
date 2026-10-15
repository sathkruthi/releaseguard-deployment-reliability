import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import yaml

from releaseguard.config import (
    documents,
    drift,
    fingerprint,
    load_config,
    manifest_errors,
    projection,
)
from releaseguard.controller import Controller, app_manifest

VALID = Path("tests/fixtures/valid.yaml").read_text()


class ConfigTests(unittest.TestCase):
    def test_formats_and_schema(self):
        config = load_config("configs/local.yaml")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(config))
            self.assertEqual(load_config(path), config)
            config["policy"]["rollout_seconds"] = True
            path.write_text(yaml.safe_dump(config))
            with self.assertRaises(ValueError):
                load_config(path)
        with self.assertRaises(ValueError):
            documents("item: &recursive [*recursive]")

    def test_nonfinite_policy_rejected(self):
        config = load_config("configs/local.yaml")
        config["policy"]["maximum_error_rate"] = float("nan")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nan.yaml"
            path.write_text(yaml.safe_dump(config))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_valid_and_malformed_shapes(self):
        config = load_config("configs/local.yaml")
        self.assertEqual(manifest_errors(config, documents(VALID)), [])
        for field, value in [
            ("resources", []),
            ("securityContext", []),
            ("securityContext", {"capabilities": []}),
            ("readinessProbe", {"httpGet": []}),
        ]:
            objects = documents(VALID)
            deployment = next(o for o in objects if o["kind"] == "Deployment")
            deployment["spec"]["template"]["spec"]["containers"][0][field] = value
            self.assertTrue(manifest_errors(config, objects))

    def test_incident001_unsafe_production_manifest(self):
        config = load_config("configs/production.json")
        objects = documents(VALID)
        deployment = next(o for o in objects if o["kind"] == "Deployment")
        deployment["spec"]["replicas"] = 0
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        container["image"] = "releaseguard-sample:latest"
        container["resources"] = {}
        errors = [] if os.getenv("RG_UNSAFE_CONFIG") == "1" else manifest_errors(config, objects)
        self.assertTrue(errors, "unsafe production manifest was accepted")
        for expected in ("replicas", "image", "resources"):
            self.assertTrue(any(expected in error for error in errors), errors)

    def test_resource_and_drift_semantics(self):
        config = load_config("configs/local.yaml")
        expected = app_manifest(VALID)
        changed = copy.deepcopy(expected)
        changed["spec"]["replicas"] = 2
        diff = drift(projection(expected), projection(changed))
        self.assertEqual(diff[0]["path"], "/replicas")
        self.assertNotEqual(fingerprint(expected), fingerprint(changed))
        changed["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] = (
            "2000m"
        )
        self.assertTrue(any("resources" in error for error in manifest_errors(config, [changed])))

    def test_rejected_manifest_cannot_upgrade(self):
        cluster = Mock()
        cluster.config = load_config("configs/production.json")
        cluster.render.return_value = VALID
        result = Controller(cluster).deploy("v1", "does-not-exist.json")
        self.assertEqual(result["state"], "rejected_configuration")
        cluster.upgrade.assert_not_called()


if __name__ == "__main__":
    unittest.main()
