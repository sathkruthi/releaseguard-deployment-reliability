# Operations and recovery

Run all commands from the repository root with `.local/bin` on PATH. Never copy `.local/kubeconfig` into evidence, a ticket, or Git.

## Normal operation

`make demo` deploys v1 and records a fresh baseline after actual healthy observations. `python -m releaseguard assess` (use `.venv/bin/python`) reads the current release and generates bounded traffic. `deploy --image v2` exercises readiness failure; `deploy --image v3` exercises latency failure. Use `--report PATH` before the subcommand to persist JSON.

`make drift` compares the supported fields of rendered v1 with the live deployment. Drift is a diagnostic state, not authorization to apply arbitrary changes. JSON arrays are compared as a whole; field ordering in environment lists can therefore appear as drift.

## Incident handling

For `insufficient_evidence`, inspect `telemetry_error`, scrape health, sample counts and per-instance counter changes. Restore telemetry and assess again. Do not weaken thresholds to force rollback.

For `degraded_external_dependency`, inspect the separate dependency. The app revision is unchanged in the demonstration, so app rollback offers no demonstrated repair. The controlled fault command requires an explicit opt-in:

```bash
.venv/bin/python -m releaseguard dependency --down --enable-local-faults
.venv/bin/python -m releaseguard --report .local/outage.json assess
.venv/bin/python -m releaseguard dependency --enable-local-faults
.venv/bin/python -m releaseguard --report .local/restored.json assess
```

A successful dependency rollout can precede endpoint/connection convergence. Actual work requests may still fail briefly. Preserve the first observation, wait, and assess a new complete window. The integration harness allows at most three recovery observations and retains them all.

For `mixed_failure` or `unattributed_degradation`, investigate rather than guessing. For `recovery_unverified`, inspect current Helm history and deployment before further changes: a timed-out command can have partially applied a rollback. `rollback_performed: null` means its completion is uncertain. `true` means the command completed, not necessarily healthy recovery. Only `state: recovered` establishes the documented checks.

## Local inspection and cleanup

All inspection should specify `--kubeconfig .local/kubeconfig --context kind-releaseguard --namespace releaseguard-demo`. For example:

```bash
kubectl --kubeconfig .local/kubeconfig --context kind-releaseguard --namespace releaseguard-demo get pods
helm --kubeconfig .local/kubeconfig --kube-context kind-releaseguard --namespace releaseguard-demo history releaseguard-demo
```

To remove only this demo, first verify ownership with `.venv/bin/python -m releaseguard assess`, then use `kind delete cluster --name releaseguard --kubeconfig .local/kubeconfig`. This deletes the demo's local state and metrics. Remove `.local/ownership.json` and `.local/baseline.json` afterward before creating a new cluster. Keep any sanitized incident reports you need. No automated command deletes unrelated stacks or volumes.

If `kind load docker-image` reports missing foreign-platform content, use `make images`: it exports each native platform with `docker image save --platform linux/amd64` before importing the archive. Older Docker versions without that option are outside the reference setup.
