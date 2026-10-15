# INCIDENT-001 — Syntactically valid but unsafe configuration

**Controlled fixture, not a historical production incident.** A production-profile manifest with zero replicas, a mutable `latest` image, and missing resource bounds is syntactically valid YAML but violates deployment policy.

A parse-only test variant accepts it and fails the acceptance test. The corrected validator reports explicit replica/image/resource paths before any Helm upgrade. `tests/test_config.py` also verifies that a rejected candidate never invokes upgrade, and that both JSON/YAML configurations obey the same schema.

Reproduce: `PYTHONPATH=. .venv/bin/python scripts/regressions.py`, then `make incident ID=001`. Inspect `evidence/regressions/001-unsafe.txt`, `001-corrected.txt`, and `evidence/incident001.json`.

Acceptance: all three policy violations are reported; no mutation is invoked for rejected manifests. The production profile remains local validation-only. Review additionally found that YAML non-finite numbers could bypass ordinary comparisons; finite-threshold rejection now has an executable regression test.
