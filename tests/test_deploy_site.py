"""deploy_site.py commits the built pages to the site branch without a checkout.

The pages are built from gitignored data, so they can't be built in CI. The
deploy commits them to a branch that holds only the site, and the Pages
workflow publishes that branch. These tests run the commit step against a
scratch repository.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deploy_site.py"


def load_script():
    spec = importlib.util.spec_from_file_location("deploy_site", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deploy_site"] = module
    spec.loader.exec_module(module)
    return module


deploy = load_script()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def scratch_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "test@example.com")
    git(repo, "config", "user.name", "test")
    (repo / "code.py").write_text("print('hi')\n")
    git(repo, "add", "code.py")
    git(repo, "commit", "-q", "-m", "code")
    return repo


def built(tmp_path: Path, name: str, files: dict[str, str]) -> Path:
    out = tmp_path / name
    for path, text in files.items():
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_text(text)
    return out


class TestCommitSite:
    def test_the_branch_holds_only_the_site(self, tmp_path):
        repo = scratch_repo(tmp_path)
        out = built(tmp_path, "out", {"methodology.html": "<p>one</p>"})
        deploy.commit_site(repo, out, "site", "deploy")
        assert git(repo, "ls-tree", "--name-only", "site").split() == [
            "methodology.html"
        ]
        assert git(repo, "show", "site:methodology.html") == "<p>one</p>"

    def test_the_checkout_is_untouched(self, tmp_path):
        repo = scratch_repo(tmp_path)
        out = built(tmp_path, "out", {"methodology.html": "<p>one</p>"})
        deploy.commit_site(repo, out, "site", "deploy")
        assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"
        assert git(repo, "status", "--porcelain") == ""

    def test_a_second_deploy_builds_on_the_first(self, tmp_path):
        repo = scratch_repo(tmp_path)
        first = deploy.commit_site(
            repo, built(tmp_path, "a", {"methodology.html": "one"}), "site", "deploy"
        )
        second = deploy.commit_site(
            repo, built(tmp_path, "b", {"methodology.html": "two"}), "site", "deploy"
        )
        assert git(repo, "rev-parse", f"{second}^") == first

    def test_a_page_the_build_stopped_writing_is_removed(self, tmp_path):
        repo = scratch_repo(tmp_path)
        deploy.commit_site(
            repo,
            built(tmp_path, "a", {"methodology.html": "x", "old.html": "y"}),
            "site",
            "deploy",
        )
        deploy.commit_site(
            repo, built(tmp_path, "b", {"methodology.html": "x"}), "site", "deploy"
        )
        assert git(repo, "ls-tree", "--name-only", "site").split() == [
            "methodology.html"
        ]

    def test_subdirectories_are_kept(self, tmp_path):
        repo = scratch_repo(tmp_path)
        out = built(tmp_path, "out", {"hero/ivy.html": "<p>ivy</p>"})
        deploy.commit_site(repo, out, "site", "deploy")
        assert git(repo, "show", "site:hero/ivy.html") == "<p>ivy</p>"
