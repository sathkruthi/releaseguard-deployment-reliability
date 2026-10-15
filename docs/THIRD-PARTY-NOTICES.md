# Third-party components

Original project code is intentionally unlicensed at the owner's request. No open-source license is granted for that code. Dependency licenses remain in force.

Runtime Python dependencies and pinned versions are in `requirements.txt`; their installed license texts are retained under `docs/licenses/`. The Go sample uses the Go standard library; its BSD-style license is included there. Development-only tools remain separate in `requirements-dev.txt`.

The demonstration downloads, rather than vendors, Docker images and local tools: Kubernetes/kind, Helm, Prometheus (Apache-2.0), Go (BSD-style), and Alpine Linux (packages have individual licenses). Their upstream distributions retain their notices. Tool downloads are pinned and checksum-verified in `scripts/tools.sh`; the kind node is pinned by digest in `deploy/kind.yaml`. Application base images and Prometheus use version tags, so their resolved build layers may change; this is a documented reproducibility limit.
