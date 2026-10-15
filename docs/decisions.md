# Technical decisions

1. **kind and Helm over a simulated deployment API.** Real rollout failures and stored Helm revisions make recovery inspectable. Cost: image downloads, Docker privileges, and one-node limits.
2. **Independent dependency deployment.** The app rollback cannot accidentally restore the dependency. This makes failure attribution observable and avoids conflating app and dependency repair.
3. **Prometheus cumulative counters and bucket deltas.** Fresh windows avoid counting historical failures as current ones. Instance-level checks detect resets masked by an increasing aggregate. Cost: one-second scrape lag and conservative inconclusive windows during pod turnover.
4. **Eligibility is narrower than degradation.** A bad status is not enough to justify a mutation. Require a changed template, measured baseline, healthy dependency and candidate evidence. Readiness failure uses candidate metrics without sending service traffic to an unready pod.
5. **Recovery is a separate measurement.** Helm success is a command result. Restored template, rollout availability, and fresh traffic establish recovery. A partial command remains uncertain.
6. **Fixed local authorization scope.** Explicit identity checks and a container ownership record prevent accidental adoption of a similarly named cluster. This is an owner-operated demonstration, not a hostile-user security boundary or a production approval system.
7. **Small Go sample, Python orchestration.** The sample has no third-party Go dependency; Python's schema library handles structural validation. Commands use argument arrays. No always-running privileged controller is required.
