"""The mock driver's checks, in one command: lint, then its unit tests.

    python tests/mock_zmart_driver/testing/run_ci.py

Run from anywhere. It checks the code with ruff and runs testing/unit/
against the mock API; there is no microscope, so no hardware stage. Exits
with the first failure's code.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DRIVER = Path(__file__).resolve().parents[1]
REPOSITORY = DRIVER.parents[1]


def main() -> int:
    for step in (
        [sys.executable, "-m", "ruff", "check", str(DRIVER)],
        [sys.executable, "-m", "pytest", "-q", str(DRIVER / "testing" / "unit")],
    ):
        print("$", " ".join(step[2:]), flush=True)
        code = subprocess.call(step, cwd=REPOSITORY)
        if code:
            return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
