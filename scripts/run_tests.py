#!/usr/bin/env python
"""Run the test suite.

Wrapper exists because the system Python has a `typeguard` install that
imports `ast.Str` (removed in 3.12+), so pytest's plugin autoload crashes on
import under 3.14. We disable third-party plugin autoloading, which must
happen before the interpreter imports pytest.

Usage:  python scripts/run_tests.py [pytest args...]
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

env = dict(os.environ)
env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
env["PYTHONPATH"] = str(ROOT / "src")

args = sys.argv[1:] or ["tests/", "-q"]
sys.exit(subprocess.call([sys.executable, "-m", "pytest", *args], cwd=ROOT, env=env))
