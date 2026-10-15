import json
import os
from pathlib import Path
import subprocess
from urllib.parse import urlparse


class CommandError(RuntimeError):
    pass


def run(command, timeout=60, check=True):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise CommandError(command[0] + " failed: " + result.stderr[-800:])
    return result


def verify_target(context, server, docker_endpoint, clusters, labels, mapping):
    address = urlparse(server)
    if context != "kind-releaseguard" or address.scheme != "https" or address.hostname != "127.0.0.1" or address.username or address.password:
        raise CommandError("refusing non-local or unrelated Kubernetes target")
    if not docker_endpoint.startswith("unix://") or "releaseguard" not in clusters:
        raise CommandError("dedicated local kind cluster not found")
    if labels.get("io.x-k8s.kind.cluster") != "releaseguard" or labels.get("io.x-k8s.kind.role") != "control-plane":
        raise CommandError("control-plane container identity mismatch")
    expected = "127.0.0.1:" + str(address.port)
    if mapping.strip() != expected:
        raise CommandError("Kubernetes API endpoint does not match the dedicated local container")
    return {"context": context, "server": server, "container": "releaseguard-control-plane"}


class Cluster:
    def __init__(self, config, kubeconfig=".local/kubeconfig"):
        self.config = config
        self.kubeconfig = str(Path(kubeconfig).resolve())

    def kubectl(self, args, timeout=60, check=True):
        return run(["kubectl", "--kubeconfig", self.kubeconfig, "--context", self.config["context"], "--namespace", self.config["namespace"], *args], timeout, check)

    def helm(self, args, timeout=90, check=True):
        return run(["helm", "--kubeconfig", self.kubeconfig, "--kube-context", self.config["context"], "--namespace", self.config["namespace"], *args], timeout, check)

    def guard(self):
        contexts = json.loads(run(["docker", "context", "inspect"]).stdout)
        endpoint = contexts[0]["Endpoints"]["docker"]["Host"]
        clusters = run(["kind", "get", "clusters"]).stdout.splitlines()
        labels = json.loads(run(["docker", "inspect", "--format", "{{json .Config.Labels}}", "releaseguard-control-plane"]).stdout)
        mapping = run(["docker", "port", "releaseguard-control-plane", "6443/tcp"]).stdout
        # No --raw: never print or persist client certificates or private keys.
        config = json.loads(self.kubectl(["config", "view", "--minify", "-o", "json"]).stdout)
        server = config["clusters"][0]["cluster"]["server"]
        return verify_target(self.config["context"], server, endpoint, clusters, labels, mapping)

    def deployment(self, name=None):
        return json.loads(self.kubectl(["get", "deployment", name or self.config["release"], "-o", "json"]).stdout)

    def rollout(self, timeout=None):
        seconds = timeout or self.config["policy"]["rollout_seconds"]
        return self.kubectl(["rollout", "status", "deployment/" + self.config["release"], "--timeout=" + str(seconds) + "s"], seconds + 10, check=False).returncode == 0

    def history(self):
        return json.loads(self.helm(["history", self.config["release"], "-o", "json"]).stdout)

    def revision(self):
        return max(int(item["revision"]) for item in self.history())

    def render(self, image):
        if image not in {"v1", "v2", "v3"}:
            raise ValueError("only local sample versions v1/v2/v3 are supported")
        return run(["helm", "template", self.config["release"], "charts/sample", "--namespace", self.config["namespace"], "--set", "image.tag=" + image]).stdout

    def upgrade(self, image):
        self.guard()
        return self.helm(["upgrade", "--install", self.config["release"], "charts/sample", "--set", "image.tag=" + image, "--timeout", str(self.config["policy"]["rollout_seconds"]) + "s"])

    def rollback(self, revision):
        self.guard()
        if type(revision) is not int or revision < 1 or revision >= self.revision():
            raise CommandError("invalid recorded rollback revision")
        return self.helm(["rollback", self.config["release"], str(revision), "--wait", "--timeout", str(self.config["policy"]["rollout_seconds"]) + "s"], self.config["policy"]["rollout_seconds"] + 15)


def create_cluster(kubeconfig=".local/kubeconfig"):
    endpoint = json.loads(run(["docker", "context", "inspect"]).stdout)[0]["Endpoints"]["docker"]["Host"]
    if not endpoint.startswith("unix://"):
        raise CommandError("cluster creation is restricted to a local Docker context")
    path = Path(kubeconfig).resolve()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    clusters = run(["kind", "get", "clusters"]).stdout.splitlines()
    if "releaseguard" in clusters:
        run(["kind", "export", "kubeconfig", "--name", "releaseguard", "--kubeconfig", str(path)])
    else:
        run(["kind", "create", "cluster", "--name", "releaseguard", "--config", "deploy/kind.yaml", "--kubeconfig", str(path), "--wait", "120s"], timeout=240)
    os.chmod(path, 0o600)
