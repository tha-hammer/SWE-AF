"""Behavior 3: deterministic manifest detector (pure — no LLM, no network).

``detect_project_commands(worktree)`` inspects project manifests and returns a
``{kind: command}`` dict. Precedence when several coexist (first present wins):
Cargo > go > pyproject/setup.py > package.json > Makefile. tmp_path-driven.
"""

import pytest

from swe_af.execution.deterministic_check import (
    ResolvedCheck,
    check_requires_test_db,
    command_supplies_test_db,
    detect_project_commands,
    resolve_issue_commands,
)

pytestmark = pytest.mark.unit


def _write(tmp_path, name, content=""):
    (tmp_path / name).write_text(content)
    return str(tmp_path)


def test_pyproject_detects_pytest(tmp_path):
    root = _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    assert detect_project_commands(root) == {"test": "pytest"}


def test_setup_py_detects_pytest(tmp_path):
    root = _write(tmp_path, "setup.py", "from setuptools import setup\nsetup()\n")
    assert detect_project_commands(root) == {"test": "pytest"}


def test_go_mod_detects_go_commands(tmp_path):
    root = _write(tmp_path, "go.mod", "module example.com/x\n")
    assert detect_project_commands(root) == {"build": "go build ./...", "test": "go test ./..."}


def test_cargo_detects_cargo_commands(tmp_path):
    root = _write(tmp_path, "Cargo.toml", "[package]\nname = 'x'\n")
    assert detect_project_commands(root) == {"build": "cargo build", "test": "cargo test"}


def test_package_json_with_test_script(tmp_path):
    root = _write(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    assert detect_project_commands(root) == {"test": "npm test"}


def test_package_json_with_build_and_test(tmp_path):
    root = _write(tmp_path, "package.json", '{"scripts": {"build": "tsc", "test": "jest"}}')
    assert detect_project_commands(root) == {"build": "npm run build", "test": "npm test"}


def test_package_json_without_test_script(tmp_path):
    root = _write(tmp_path, "package.json", '{"scripts": {"lint": "eslint ."}}')
    assert detect_project_commands(root) == {}


def test_package_json_malformed_returns_empty(tmp_path):
    root = _write(tmp_path, "package.json", "{not valid json")
    assert detect_project_commands(root) == {}


def test_makefile_with_test_target(tmp_path):
    root = _write(tmp_path, "Makefile", "build:\n\tgo build\n\ntest:\n\tpytest\n")
    assert detect_project_commands(root) == {"test": "make test"}


def test_makefile_without_test_target(tmp_path):
    root = _write(tmp_path, "Makefile", "build:\n\tgo build\n")
    assert detect_project_commands(root) == {}


def test_no_manifest_returns_empty(tmp_path):
    assert detect_project_commands(str(tmp_path)) == {}


def test_nonexistent_path_returns_empty(tmp_path):
    assert detect_project_commands(str(tmp_path / "nope")) == {}


def test_precedence_cargo_over_pyproject(tmp_path):
    _write(tmp_path, "Cargo.toml", "[package]\nname = 'x'\n")
    root = _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    assert detect_project_commands(root) == {"build": "cargo build", "test": "cargo test"}


def test_precedence_pyproject_over_package_json(tmp_path):
    _write(tmp_path, "pyproject.toml", "[project]\nname = 'x'\n")
    root = _write(tmp_path, "package.json", '{"scripts": {"test": "jest"}}')
    assert detect_project_commands(root) == {"test": "pytest"}


def test_deterministic_idempotent(tmp_path):
    root = _write(tmp_path, "go.mod", "module x\n")
    first = detect_project_commands(root)
    second = detect_project_commands(root)
    assert first == second == {"build": "go build ./...", "test": "go test ./..."}


# ---------------------------------------------------------------------------
# Behavior 5: resolve_issue_commands (typed-first, manifest-fallback)
# ---------------------------------------------------------------------------


def _issue(**kw):
    base = {"name": "lexer", "title": "Lexer", "description": "d", "acceptance_criteria": ["a"]}
    base.update(kw)
    return base


def test_planned_verification_wins(tmp_path):
    issue = _issue(verification=[{"description": "d", "command": "pytest -k lexer", "kind": "test"}])
    resolved = resolve_issue_commands(issue, str(tmp_path))
    assert resolved == [ResolvedCheck(command="pytest -k lexer", source="planned")]


def test_planned_wins_over_manifest(tmp_path):
    # A pyproject manifest is present, but the planner's typed check is more specific.
    _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    issue = _issue(verification=[{"description": "d", "command": "pytest -k lexer", "kind": "test"}])
    resolved = resolve_issue_commands(issue, str(tmp_path))
    assert [r.source for r in resolved] == ["planned"]
    assert resolved[0].command == "pytest -k lexer"


def test_manifest_fallback_when_no_verification(tmp_path):
    root = _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    resolved = resolve_issue_commands(_issue(), root)
    assert resolved == [ResolvedCheck(command="pytest", source="manifest")]


def test_manifest_fallback_orders_test_then_build(tmp_path):
    root = _write(tmp_path, "go.mod", "module x\n")
    resolved = resolve_issue_commands(_issue(), root)
    assert resolved == [
        ResolvedCheck(command="go test ./...", source="manifest"),
        ResolvedCheck(command="go build ./...", source="manifest"),
    ]


def test_empty_when_no_verification_and_no_manifest(tmp_path):
    assert resolve_issue_commands(_issue(), str(tmp_path)) == []


def test_invalid_planned_commands_fall_back_to_manifest(tmp_path):
    # Shouldn't happen post-B1, but defensively: empty/whitespace commands are
    # treated as absent, so manifest fallback applies.
    root = _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    issue = _issue(verification=[{"description": "d", "command": "   ", "kind": "test"}])
    resolved = resolve_issue_commands(issue, root)
    assert resolved == [ResolvedCheck(command="pytest", source="manifest")]


def test_resolution_is_pure_idempotent(tmp_path):
    root = _write(tmp_path, "pyproject.toml", "[project]\nname='x'\n")
    issue = _issue(verification=[{"description": "d", "command": "pytest -q", "kind": "test"}])
    assert resolve_issue_commands(issue, root) == resolve_issue_commands(issue, root)


def test_planned_check_declares_database_requirement():
    assert check_requires_test_db("REQUIRE_TEST_DB=1 npm run test:integration")
    assert check_requires_test_db("DATABASE_URL_TEST=postgres://x npm test")
    assert command_supplies_test_db("DATABASE_URL_TEST=postgres://x npm test")
    assert not command_supplies_test_db("REQUIRE_TEST_DB=1 npm test")
    assert not check_requires_test_db("npm test")
