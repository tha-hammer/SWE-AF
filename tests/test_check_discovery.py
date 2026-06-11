"""Behavior 3: deterministic manifest detector (pure — no LLM, no network).

``detect_project_commands(worktree)`` inspects project manifests and returns a
``{kind: command}`` dict. Precedence when several coexist (first present wins):
Cargo > go > pyproject/setup.py > package.json > Makefile. tmp_path-driven.
"""

import pytest

from swe_af.execution.deterministic_check import detect_project_commands

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
