"""Unsafe policies are isolated test variants, never runtime flags."""

import os
import subprocess
import sys
from pathlib import Path

cases = [
    (
        "002",
        "RG_UNSAFE_RECOVERY",
        "test_controller.RecoveryTests.test_command_success_does_not_prove_recovery",
    ),
    (
        "001",
        "RG_UNSAFE_CONFIG",
        "test_config.ConfigTests.test_incident001_unsafe_production_manifest",
    ),
    (
        "003",
        "RG_UNSAFE_ROLLBACK",
        "test_policy.DecisionTests.test_incident003_dependency_does_not_rollback",
    ),
]
output = Path(".local/regressions")
output.mkdir(parents=True, exist_ok=True)
for incident, flag, test in cases:
    for unsafe in (True, False):
        env = dict(os.environ, PYTHONPATH=".:tests")
        env.pop(flag, None)
        if unsafe:
            env[flag] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "unittest", test, "-v"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        state = "unsafe" if unsafe else "corrected"
        (output / (incident + "-" + state + ".txt")).write_text(result.stdout + result.stderr)
        assert (result.returncode != 0) == unsafe, incident + ": unexpected regression result"
        print(incident + "-" + state + ": expected " + ("failure" if unsafe else "pass"))
