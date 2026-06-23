"""Guard against ``run_git_init`` re-initializing a repo that already has
history (observed: an existing repo was ``git init``-clobbered to a fresh
``main`` + "Initial commit", destroying its real branch/remote/history).

These cover the load-bearing deterministic detection helper that drives the
pre-prompt hard constraint and the post-run survival check.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from swe_af.reasoners.execution_agents import _detect_existing_repo


def _git(cwd: str, *args: str) -> None:
    subprocess.run(
        ["git", "-C", cwd, *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _make_repo_with_commit(path: str, branch: str = "work") -> str:
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@t.io")
    _git(path, "config", "user.name", "t")
    _git(path, "checkout", "-q", "-b", branch)
    Path(path, "f.txt").write_text("hi")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "init")
    return subprocess.run(
        ["git", "-C", path, "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()


def test_detects_existing_repo_with_history() -> None:
    with tempfile.TemporaryDirectory() as d:
        head = _make_repo_with_commit(d, branch="feature/x")
        result = _detect_existing_repo(d)
        assert result is not None
        sha, branch = result
        assert sha == head
        assert branch == "feature/x"


def test_fresh_folder_is_not_existing() -> None:
    # A plain directory with no .git → genuinely fresh; agent may `git init`.
    with tempfile.TemporaryDirectory() as d:
        Path(d, "readme.md").write_text("hi")
        assert _detect_existing_repo(d) is None


def test_initialized_but_no_commits_is_not_existing() -> None:
    # `git init` but no commit yet → nothing to destroy; safe to treat fresh.
    with tempfile.TemporaryDirectory() as d:
        _git(d, "init", "-q")
        assert _detect_existing_repo(d) is None


def test_nonexistent_path_does_not_crash() -> None:
    # Fail-safe: undeterminable state must not raise (returns the sentinel).
    result = _detect_existing_repo("/nonexistent/path/should/not/exist")
    assert result is None or result == ("unknown", "unknown")
