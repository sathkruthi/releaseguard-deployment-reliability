import argparse
import json
import subprocess
import sys

import yaml

from .cluster import Cluster, CommandError, create_cluster
from .config import documents, load_config, manifest_errors
from .controller import Controller, save


def main():
    parser = argparse.ArgumentParser(description="Guarded local Kubernetes release verification")
    parser.add_argument("--config", default="configs/local.yaml")
    parser.add_argument("--kubeconfig", default=".local/kubeconfig")
    parser.add_argument("--report")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cluster")
    sub.add_parser("bootstrap")
    check = sub.add_parser("check")
    check.add_argument("--manifest", required=True)
    base = sub.add_parser("baseline")
    base.add_argument("--output", default=".local/baseline.json")
    assess = sub.add_parser("assess")
    assess.add_argument("--baseline", default=".local/baseline.json")
    deploy = sub.add_parser("deploy")
    deploy.add_argument("--image", choices=["v1", "v2", "v3"], required=True)
    deploy.add_argument("--baseline", default=".local/baseline.json")
    deploy.add_argument("--no-rollback", action="store_true")
    drift = sub.add_parser("drift")
    drift.add_argument("--image", default="v1", choices=["v1", "v2", "v3"])
    fault = sub.add_parser("dependency")
    fault.add_argument("--down", action="store_true")
    fault.add_argument("--enable-local-faults", action="store_true", required=True)
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        cluster = Cluster(config, args.kubeconfig)
        controller = Controller(cluster)
        if args.command == "cluster":
            create_cluster(args.kubeconfig)
            result = {"state": "cluster_ready", "identity": cluster.guard()}
        elif args.command == "check":
            from pathlib import Path

            errors = manifest_errors(config, documents(Path(args.manifest).read_text()))
            result = {
                "state": "rejected_configuration" if errors else "validated",
                "errors": errors,
            }
        elif args.command == "bootstrap":
            result = controller.bootstrap()
        elif args.command == "baseline":
            result = {
                "state": "baseline_verified",
                "baseline": controller.baseline(args.output),
            }
        elif args.command == "assess":
            result = controller.assess(args.baseline)
        elif args.command == "deploy":
            result = controller.deploy(args.image, args.baseline, not args.no_rollback)
        elif args.command == "drift":
            result = controller.drift(args.image)
        else:
            result = controller.dependency_fault(args.down)
        if args.report:
            save(args.report, result)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return (
            0
            if result["state"]
            in {
                "validated",
                "cluster_ready",
                "bootstrapped",
                "baseline_verified",
                "healthy",
                "recovered",
                "in_sync",
                "dependency_fault_enabled",
                "dependency_restored",
            }
            else 2
        )
    except (
        OSError,
        ValueError,
        KeyError,
        CommandError,
        subprocess.TimeoutExpired,
        yaml.YAMLError,
    ) as error:
        result = {
            "state": "command_failed",
            "error": str(error),
            "rollback_performed": False,
        }
        if args.report:
            save(args.report, result)
        print(json.dumps(result, indent=2, allow_nan=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
