import copy
import hashlib
import json
import math
import re
from pathlib import Path

import jsonschema
import yaml

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["environment", "context", "namespace", "release", "policy"],
    "properties": {
        "environment": {"enum": ["local", "production"]},
        "context": {"const": "kind-releaseguard"},
        "namespace": {"const": "releaseguard-demo"},
        "release": {"const": "releaseguard-demo"},
        "policy": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "rollout_seconds",
                "minimum_requests",
                "maximum_error_rate",
                "maximum_p95_seconds",
            ],
            "properties": {
                "rollout_seconds": {"type": "integer", "minimum": 10, "maximum": 120},
                "minimum_requests": {"type": "integer", "minimum": 20, "maximum": 200},
                "maximum_error_rate": {"type": "number", "minimum": 0, "maximum": 0.2},
                "maximum_p95_seconds": {
                    "type": "number",
                    "minimum": 0.05,
                    "maximum": 2,
                },
            },
        },
    },
}


def documents(text):
    if len(text.encode()) > 262144:
        raise ValueError("document exceeds 256 KiB")
    if any(
        isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken))
        for token in yaml.scan(text)
    ):
        raise ValueError("YAML anchors and aliases are not supported")
    result = [document for document in yaml.safe_load_all(text) if document is not None]
    if len(result) > 32 or any(not isinstance(document, dict) for document in result):
        raise ValueError("expected at most 32 mapping documents")
    return result


def load_config(path):
    configs = documents(Path(path).read_text())
    if len(configs) != 1:
        raise ValueError("one configuration document required")
    errors = sorted(
        jsonschema.Draft202012Validator(SCHEMA).iter_errors(configs[0]),
        key=lambda e: str(list(e.path)),
    )
    if errors:
        raise ValueError("; ".join("/".join(map(str, e.path)) + ": " + e.message for e in errors))
    if any(
        isinstance(value, float) and not math.isfinite(value)
        for value in configs[0]["policy"].values()
    ):
        raise ValueError("policy values must be finite")
    return configs[0]


def manifest_errors(config, objects):
    errors = []
    shape = {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "metadata": {"type": "object"},
            "spec": {"type": "object"},
        },
    }
    for obj in objects:
        for error in jsonschema.Draft202012Validator(shape).iter_errors(obj):
            errors.append("manifest/" + "/".join(map(str, error.path)) + ": " + error.message)
    if errors:
        return errors
    deployments = [obj for obj in objects if obj.get("kind") == "Deployment"]
    if len(deployments) != 1:
        return ["manifest: exactly one app Deployment required"]
    for obj in objects:
        metadata = obj.get("metadata", {})
        if obj.get("kind") not in {"Deployment", "Service"}:
            errors.append("manifest: only app Deployment and Services are permitted")
        if metadata.get("namespace") != config["namespace"]:
            errors.append("metadata.namespace: must match authorized local namespace")
        allowed = {config["release"], config["release"] + "-metrics"}
        if metadata.get("name") not in allowed:
            errors.append("metadata.name: unrelated resource is not authorized")
    deployment = deployments[0]
    spec = deployment.get("spec", {})
    pod_shape = {
        "type": "object",
        "properties": {
            "template": {
                "type": "object",
                "properties": {
                    "metadata": {"type": "object"},
                    "spec": {
                        "type": "object",
                        "properties": {
                            "containers": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "image": {"type": "string"},
                                        "resources": {
                                            "type": "object",
                                            "properties": {
                                                "requests": {"type": "object"},
                                                "limits": {"type": "object"},
                                            },
                                        },
                                        "securityContext": {
                                            "type": "object",
                                            "properties": {
                                                "capabilities": {
                                                    "type": "object",
                                                    "properties": {
                                                        "drop": {
                                                            "type": "array",
                                                            "items": {"type": "string"},
                                                        },
                                                        "add": {
                                                            "type": "array",
                                                            "items": {"type": "string"},
                                                        },
                                                    },
                                                }
                                            },
                                        },
                                        "readinessProbe": {
                                            "type": "object",
                                            "properties": {"httpGet": {"type": "object"}},
                                        },
                                        "livenessProbe": {
                                            "type": "object",
                                            "properties": {"httpGet": {"type": "object"}},
                                        },
                                    },
                                },
                            },
                            "volumes": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                },
            }
        },
    }
    for error in jsonschema.Draft202012Validator(pod_shape).iter_errors(spec):
        errors.append("spec/" + "/".join(map(str, error.path)) + ": " + error.message)
    if errors:
        return errors
    replicas = spec.get("replicas", 1)
    minimum = 2 if config["environment"] == "production" else 1
    if type(replicas) is not int or not minimum <= replicas <= 3:
        errors.append(f"spec.replicas: {config['environment']} requires {minimum}..3 replicas")
    pod = spec.get("template", {}).get("spec", {})
    if (
        pod.get("automountServiceAccountToken") is not False
        or pod.get("initContainers")
        or pod.get("ephemeralContainers")
        or pod.get("volumes")
    ):
        errors.append(
            "spec.template.spec: tokens, extra containers, and volumes are not permitted for this sample"
        )
    if any(pod.get(key, False) for key in ("hostNetwork", "hostPID", "hostIPC")):
        errors.append("spec.template.spec: host access is forbidden")
    if any("hostPath" in volume for volume in pod.get("volumes", [])):
        errors.append("spec.template.spec.volumes: hostPath is forbidden")
    containers = pod.get("containers", [])
    if len(containers) != 1:
        errors.append("spec.template.spec.containers: exactly one app container required")
    for container in containers:
        prefix = "spec.template.spec.containers/" + str(container.get("name", "?"))
        image = container.get("image", "")
        if config["environment"] == "production":
            valid_image = bool(re.fullmatch(r"releaseguard-sample@sha256:[a-f0-9]{64}", image))
        else:
            valid_image = bool(re.fullmatch(r"releaseguard-sample:v[1-3]", image))
        if not valid_image:
            errors.append(
                prefix + "/image: versioned local image required; production requires a digest"
            )
        resources = container.get("resources", {})
        for category in ("requests", "limits"):
            for resource in ("cpu", "memory"):
                if not resources.get(category, {}).get(resource):
                    errors.append(prefix + f"/resources/{category}/{resource}: required")
        try:

            def cpu(value):
                return (
                    int(str(value)[:-1])
                    if re.fullmatch(r"[0-9]+m", str(value))
                    else int(str(value)) * 1000
                )

            def memory(value):
                return (
                    int(str(value)[:-2]) * (1024 if str(value).endswith("Gi") else 1)
                    if re.fullmatch(r"[0-9]+(?:Mi|Gi)", str(value))
                    else 0
                )

            request_cpu, limit_cpu = [cpu(resources[key]["cpu"]) for key in ("requests", "limits")]
            request_mem, limit_mem = [
                memory(resources[key]["memory"]) for key in ("requests", "limits")
            ]
            if (
                not 10 <= request_cpu <= limit_cpu <= 1000
                or not 16 <= request_mem <= limit_mem <= 256
            ):
                errors.append(
                    prefix
                    + "/resources: require 10m..1000m CPU and 16Mi..256Mi memory with requests <= limits"
                )
        except (KeyError, ValueError, TypeError):
            errors.append(prefix + "/resources: unsupported or missing resource quantity")
        security = container.get("securityContext", {})
        if (
            security.get("runAsNonRoot") is not True
            or security.get("readOnlyRootFilesystem") is not True
            or security.get("allowPrivilegeEscalation") is not False
            or security.get("privileged", False)
            or security.get("capabilities", {}).get("add")
            or "ALL" not in security.get("capabilities", {}).get("drop", [])
        ):
            errors.append(
                prefix
                + "/securityContext: non-root, read-only, no escalation, and dropped capabilities required"
            )
        for probe in ("readinessProbe", "livenessProbe"):
            p = container.get(probe, {})
            if (
                not p.get("httpGet", {}).get("path")
                or type(p.get("timeoutSeconds")) is not int
                or not 1 <= p["timeoutSeconds"] <= 3
            ):
                errors.append(prefix + f"/{probe}: bounded HTTP probe required")
            if (
                p.get("httpGet", {}).get("host")
                or p.get("httpGet", {}).get("port") != 8080
                or p.get("httpGet", {}).get("path")
                != ("/ready" if probe == "readinessProbe" else "/live")
            ):
                errors.append(prefix + f"/{probe}: sample-local endpoint required")
        if (
            container.get("command")
            or container.get("args")
            or container.get("lifecycle")
            or container.get("envFrom")
        ):
            errors.append(prefix + ": custom commands, lifecycle hooks and envFrom are forbidden")
    return errors


def projection(deployment):
    spec = deployment.get("spec", {})
    containers = []
    for c in spec.get("template", {}).get("spec", {}).get("containers", []):
        item = {
            key: copy.deepcopy(c.get(key, {} if key in {"resources", "securityContext"} else []))
            for key in ("env", "resources", "securityContext", "ports")
        }
        item.update(
            {
                "name": c.get("name"),
                "image": c.get("image"),
                "imagePullPolicy": c.get("imagePullPolicy", "IfNotPresent"),
            }
        )
        for probe in ("readinessProbe", "livenessProbe"):
            p = c.get(probe, {})
            item[probe] = {
                "path": p.get("httpGet", {}).get("path"),
                "port": p.get("httpGet", {}).get("port"),
                "timeoutSeconds": p.get("timeoutSeconds", 1),
                "periodSeconds": p.get("periodSeconds", 10),
                "failureThreshold": p.get("failureThreshold", 3),
            }
        # Kubernetes adds default port protocol and security defaults; compare the supported intent.
        item["ports"] = [
            {
                "containerPort": p.get("containerPort"),
                "name": p.get("name"),
                "protocol": p.get("protocol", "TCP"),
            }
            for p in item["ports"]
        ]
        containers.append(item)
    pod = spec.get("template", {}).get("spec", {})
    return {
        "replicas": spec.get("replicas", 1),
        "containers": sorted(containers, key=lambda c: c["name"]),
        "pod": {
            key: pod.get(key, key == "automountServiceAccountToken")
            for key in (
                "automountServiceAccountToken",
                "hostNetwork",
                "hostPID",
                "hostIPC",
            )
        },
    }


def fingerprint(deployment):
    return hashlib.sha256(
        json.dumps(projection(deployment), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def drift(expected, actual, path=""):
    if isinstance(expected, dict) and isinstance(actual, dict):
        return [
            entry
            for key in sorted(set(expected) | set(actual))
            for entry in drift(expected.get(key), actual.get(key), path + "/" + key)
        ]
    if expected != actual:
        return [{"path": path, "expected": expected, "actual": actual}]
    return []
