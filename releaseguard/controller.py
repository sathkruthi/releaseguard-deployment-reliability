import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from . import metrics
from .cluster import CommandError
from .config import documents, drift, fingerprint, manifest_errors, projection
from .policy import Evidence, decide, report


def save(path, value):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, target)


def revision(deployment):
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    return image.rsplit(":", 1)[-1]


def ready(deployment):
    desired = deployment["spec"].get("replicas", 1)
    status = deployment.get("status", {})
    return (
        desired > 0
        and status.get("observedGeneration", 0) >= deployment["metadata"]["generation"]
        and all(
            status.get(field, 0) == desired
            for field in (
                "replicas",
                "updatedReplicas",
                "availableReplicas",
                "readyReplicas",
            )
        )
    )


def app_manifest(text):
    matches = [obj for obj in documents(text) if obj.get("kind") == "Deployment"]
    if len(matches) != 1:
        raise ValueError("exactly one recorded app deployment required")
    return matches[0]


class Controller:
    def __init__(self, cluster):
        self.cluster = cluster
        self.config = cluster.config

    def bootstrap(self):
        self.cluster.guard()
        if self.cluster.kubectl(
            ["get", "namespace", self.config["namespace"]], check=False
        ).returncode:
            self.cluster.kubectl(["create", "namespace", self.config["namespace"]])
        objects = documents(Path("deploy/infra.yaml").read_text())
        for obj in objects:
            if (
                obj.get("kind") not in {"Deployment", "ConfigMap", "Service"}
                or obj.get("metadata", {}).get("namespace") != self.config["namespace"]
                or obj.get("metadata", {}).get("name")
                not in {"releaseguard-dependency", "releaseguard-prometheus"}
            ):
                raise ValueError("unrelated infrastructure object refused")
        self.cluster.guard()
        self.cluster.kubectl(["apply", "-f", "deploy/infra.yaml"])
        for name in ("releaseguard-dependency", "releaseguard-prometheus"):
            self.cluster.kubectl(
                ["rollout", "status", "deployment/" + name, "--timeout=90s"],
                timeout=100,
            )
        rendered = self.cluster.render("v1")
        errors = manifest_errors(self.config, documents(rendered))
        if errors:
            raise ValueError("; ".join(errors))
        self.cluster.upgrade("v1")
        if not self.cluster.rollout():
            raise CommandError("initial sample rollout did not become healthy")
        return {"state": "bootstrapped", "identity": self.cluster.guard()}

    def measure(self, deployment, baseline, rollout_ready=None):
        version = revision(deployment)
        observation = None
        available, candidate_ready, reset = False, None, False
        count, errors, p95 = 0, 0, 0
        telemetry_error = None
        rollout_ready = ready(deployment) if rollout_ready is None else rollout_ready
        try:
            if rollout_ready:
                observation = metrics.observe(version, self.config["policy"]["minimum_requests"])
            else:
                snapshot = metrics.wait_snapshot(version)
                observation = {
                    "before": snapshot,
                    "after": snapshot,
                    "delta": metrics.delta(snapshot, snapshot),
                    "responses": [],
                }
            available = True
            candidate_ready = observation["after"]["ready"]
            values = observation["delta"]
            count, errors, p95, reset = (
                values["requests"],
                values["error_rate"],
                values["p95_seconds"],
                values["counter_reset"],
            )
        except (OSError, ValueError, KeyError) as error:
            telemetry_error = str(error)
        baseline_valid, baseline_error = (
            self.valid_baseline(baseline, deployment) if baseline else (False, "baseline absent")
        )
        evidence = Evidence(
            bool(baseline and fingerprint(deployment) != baseline.get("fingerprint")),
            baseline_valid,
            rollout_ready,
            candidate_ready,
            metrics.dependency_health(),
            available,
            count,
            errors,
            p95,
            reset,
        )
        result = report(evidence, decide(evidence, self.config["policy"]))
        result.update(
            {
                "observation": observation,
                "telemetry_error": telemetry_error,
                "baseline_error": baseline_error,
                "image_revision": version,
            }
        )
        return result

    def baseline(self, path):
        identity = self.cluster.guard()
        if not self.cluster.rollout():
            raise CommandError("cannot record an unavailable baseline")
        deployment = self.cluster.deployment()
        recorded = documents(self.cluster.helm(["get", "manifest", self.config["release"]]).stdout)
        errors = manifest_errors(self.config, recorded)
        if errors:
            raise ValueError("unsafe baseline manifest: " + "; ".join(errors))
        health = self.measure(deployment, None)
        if health["decision"]["state"] != "healthy":
            raise ValueError("cannot record baseline: " + json.dumps(health))
        baseline = {
            "created_at": datetime.now(UTC).isoformat(),
            "identity": identity,
            "namespace": self.config["namespace"],
            "release": self.config["release"],
            "deployment_uid": deployment["metadata"]["uid"],
            "helm_revision": self.cluster.revision(),
            "fingerprint": fingerprint(deployment),
            "image_revision": revision(deployment),
            "health": health,
        }
        save(path, baseline)
        return baseline

    def valid_baseline(self, baseline, deployment):
        try:
            if (
                baseline["health"]["decision"]["state"] != "healthy"
                or baseline["identity"] != self.cluster.guard()
                or baseline["namespace"] != self.config["namespace"]
                or baseline["release"] != self.config["release"]
                or baseline["deployment_uid"] != deployment["metadata"]["uid"]
            ):
                return False, "baseline identity or measured health does not match"
            number = baseline["helm_revision"]
            if type(number) is not int or number < 1 or number > self.cluster.revision():
                return False, "baseline revision is invalid"
            manifest = self.cluster.helm(
                ["get", "manifest", self.config["release"], "--revision", str(number)]
            ).stdout
            errors = manifest_errors(self.config, documents(manifest))
            if errors:
                return (
                    False,
                    "recorded baseline violates current manifest policy: " + "; ".join(errors),
                )
            if fingerprint(app_manifest(manifest)) != baseline["fingerprint"]:
                return False, "recorded Helm manifest disagrees with baseline"
            return True, None
        except (KeyError, ValueError, CommandError) as error:
            return False, str(error)

    def assess(self, baseline_path):
        identity = self.cluster.guard()
        baseline = json.loads(Path(baseline_path).read_text())
        deployment = self.cluster.deployment()
        result = self.measure(deployment, baseline)
        result.update(
            {
                "state": result["decision"]["state"],
                "identity": identity,
                "deployment_fingerprint": fingerprint(deployment),
                "helm_revision": self.cluster.revision(),
            }
        )
        return result

    def deploy(self, image, baseline_path, rollback=True):
        identity = self.cluster.guard()
        rendered = self.cluster.render(image)
        errors = manifest_errors(self.config, documents(rendered))
        if errors:
            return {
                "state": "rejected_configuration",
                "errors": errors,
                "rollback_performed": False,
            }
        baseline = json.loads(Path(baseline_path).read_text())
        valid, error = self.valid_baseline(baseline, self.cluster.deployment())
        if not valid:
            return {
                "state": "insufficient_evidence",
                "errors": [error],
                "rollback_performed": False,
            }
        self.cluster.upgrade(image)
        rollout_ready = self.cluster.rollout()
        deployment = self.cluster.deployment()
        result = self.measure(deployment, baseline, rollout_ready)
        result.update(
            {
                "state": result["decision"]["state"],
                "identity": identity,
                "candidate": image,
                "helm_revision": self.cluster.revision(),
                "rollback_performed": False,
            }
        )
        if rollback and result["decision"]["rollback"]:
            # Recheck recorded target and identity immediately before the mutation.
            valid, error = self.valid_baseline(baseline, self.cluster.deployment())
            if not valid:
                result.update({"state": "insufficient_evidence", "rollback_blocked": error})
                return result
            result["rollback_attempted"] = True
            result["rollback_performed"] = None
            try:
                self.cluster.rollback(baseline["helm_revision"])
                result["rollback_performed"] = True
                restored = self.cluster.deployment()
                available = self.cluster.rollout()
                recovery = self.measure(restored, baseline, available)
                restored_template = fingerprint(restored) == baseline["fingerprint"]
                result["recovery"] = recovery
                result["restored_template"] = restored_template
                result["state"] = (
                    "recovered"
                    if restored_template and recovery["decision"]["state"] == "healthy"
                    else "recovery_unverified"
                )
            except (CommandError, subprocess.TimeoutExpired, OSError) as error:
                result["state"] = "recovery_unverified"
                result["recovery_error"] = (
                    type(error).__name__
                    + ": rollback or recovery inspection did not complete; inspect the current release"
                )
        return result

    def drift(self, image):
        self.cluster.guard()
        expected = app_manifest(self.cluster.render(image))
        actual = self.cluster.deployment()
        return {
            "state": "drift" if projection(expected) != projection(actual) else "in_sync",
            "differences": drift(projection(expected), projection(actual)),
        }

    def dependency_fault(self, down):
        self.cluster.guard()
        self.cluster.kubectl(
            [
                "set",
                "env",
                "deployment/releaseguard-dependency",
                "DEPENDENCY_FAIL=" + ("1" if down else "0"),
            ]
        )
        self.cluster.kubectl(
            [
                "rollout",
                "status",
                "deployment/releaseguard-dependency",
                "--timeout=60s",
            ],
            timeout=70,
        )
        return {"state": "dependency_fault_enabled" if down else "dependency_restored"}
