"""Build and import only the local sample images and Prometheus."""

import json
import subprocess
import tempfile
from pathlib import Path

from releaseguard.cluster import Cluster, run
from releaseguard.config import load_config

cluster = Cluster(load_config("configs/local.yaml"))
cluster.guard()
for revision, mode in [("v1", "healthy"), ("v2", "broken"), ("v3", "slow")]:
    subprocess.run(
        [
            "docker",
            "build",
            "-t",
            "releaseguard-sample:" + revision,
            "--build-arg",
            "REVISION=" + revision,
            "--build-arg",
            "MODE=" + mode,
            "sample",
        ],
        check=True,
    )
subprocess.run(["docker", "pull", "prom/prometheus:v3.15.0"], check=True)
architecture = json.loads(run(["docker", "info", "--format", "{{json .Architecture}}"]).stdout)
architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(architecture, architecture)
# Export the native platform alone: kind's OCI importer otherwise may encounter
# missing foreign-platform layers in Docker's multi-platform image store.
for image in [
    "releaseguard-sample:v1",
    "releaseguard-sample:v2",
    "releaseguard-sample:v3",
    "prom/prometheus:v3.15.0",
]:
    cluster.guard()
    with tempfile.TemporaryDirectory() as directory:
        archive = str(Path(directory) / "image.tar")
        subprocess.run(
            [
                "docker",
                "image",
                "save",
                "--platform",
                "linux/" + architecture,
                "-o",
                archive,
                image,
            ],
            check=True,
        )
        subprocess.run(
            ["kind", "load", "image-archive", archive, "--name", "releaseguard"], check=True
        )
