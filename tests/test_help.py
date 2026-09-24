"""`--help` works for `deadlock` and every script, and prints readable text."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from deadlock import cli

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted((ROOT / "scripts").glob("*.py"))


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda p: p.name)
def test_every_script_prints_help_and_writes_nothing(script, tmp_path):
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("usage:")
    assert list(tmp_path.iterdir()) == []
    # The module docstring is the description, with its line breaks kept.
    printed = {line.strip() for line in result.stdout.splitlines()}
    doc = ast.get_docstring(ast.parse(script.read_text(encoding="utf-8")))
    missing = [line for line in doc.splitlines() if line.strip() not in printed]
    assert missing == []


def test_deadlock_help_keeps_the_command_list_on_separate_lines():
    text = cli.build_parser().format_help()
    assert "deadlock heroes" in text
    lines = text.splitlines()
    heroes = next(i for i, line in enumerate(lines) if "deadlock heroes" in line)
    assert "deadlock build" in lines[heroes + 1]
