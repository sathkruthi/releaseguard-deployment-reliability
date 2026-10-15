"""Real local scenarios; never silently adopt a cluster or invent a result."""

import json
import time
from pathlib import Path

from releaseguard.cluster import Cluster
from releaseguard.config import documents, load_config, manifest_errors
from releaseguard.controller import Controller, save

output = Path(".local/integration")
output.mkdir(parents=True, exist_ok=True)
cluster = Cluster(load_config("configs/local.yaml"))
controller = Controller(cluster)
baseline = output / "baseline.json"
results = {}


def record(name, result, expected):
    save(output / (name + ".json"), result)
    results[name] = result["state"]
    print(name + ": " + result["state"], flush=True)
    if result["state"] != expected:
        raise AssertionError(name + ": expected " + expected + ", see " + str(output))


record("bootstrap", controller.bootstrap(), "bootstrapped")
controller.baseline(baseline)
record("healthy", controller.assess(baseline), "healthy")
unsafe = documents(Path("tests/fixtures/valid.yaml").read_text())
deployment = next(item for item in unsafe if item["kind"] == "Deployment")
deployment["spec"]["replicas"] = 0
container = deployment["spec"]["template"]["spec"]["containers"][0]
container["image"] = "releaseguard-sample:latest"
container["resources"] = {}
errors = manifest_errors(load_config("configs/production.json"), unsafe)
assert all(any(field in error for error in errors) for field in ("replicas", "image", "resources"))
record(
    "incident001",
    {"state": "rejected_configuration", "errors": errors, "rollback_performed": False},
    "rejected_configuration",
)
record("incident002", controller.deploy("v2", baseline), "recovered")
assert json.loads((output / "incident002.json").read_text())["evidence"]["candidate_ready"] is False
controller.baseline(baseline)
try:
    controller.dependency_fault(True)
    before = cluster.revision()
    result = controller.assess(baseline)
    result["rollback_performed"] = False
    result["helm_revision_after"] = cluster.revision()
    assert before == result["helm_revision_after"]
    assert result["evidence"]["changed"] is False
    assert result["evidence"]["error_rate"] > 0.9
    record("incident003", result, "degraded_external_dependency")
finally:
    controller.dependency_fault(False)
recovery_attempts = []
for _attempt in range(3):
    recovery = controller.assess(baseline)
    recovery_attempts.append(recovery)
    if recovery["state"] == "healthy":
        break
    time.sleep(2)
save(output / "dependency-recovery-attempts.json", recovery_attempts)
record("dependency-recovered", recovery, "healthy")
controller.baseline(baseline)
record("latency-regression", controller.deploy("v3", baseline), "recovered")
assert json.loads((output / "latency-regression.json").read_text())["evidence"]["p95_seconds"] > 0.5
try:
    cluster.guard()
    cluster.kubectl(["scale", "deployment/releaseguard-demo", "--replicas=2"])
    result = controller.drift("v1")
    assert any(item["path"] == "/replicas" for item in result["differences"])
    record("drift-detected", result, "drift")
finally:
    cluster.guard()
    cluster.kubectl(["scale", "deployment/releaseguard-demo", "--replicas=1"])
    assert cluster.rollout()
record("drift-restored", controller.drift("v1"), "in_sync")
save(output / "summary.json", {"state": "passed", "scenarios": results})
