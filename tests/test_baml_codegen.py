"""SB-1: baml-py loads + baml_client generates on py3.14.

Retires the #1 risk (abi3 wheel load on 3.14) and pins the exact
`b.parse.ExtractDynamic(text, baml_options={"tb": tb})` call signature that
every later milestone references.
"""

import json
import subprocess
import sys
from pathlib import Path

import baml_py
import baml_py.errors
import pytest

pytestmark = pytest.mark.unit

VENV_BAML_CLI = Path(sys.prefix) / "bin" / "baml-cli"

# Independent oracle: hand-authored, NOT enumerated from baml_src/ at test time.
EXPECTED_FUNCTIONS = ["ExtractDynamic"]


def test_baml_py_imports_on_py314():
    """abi3 wheel loads on the SWE-AF 3.14 venv and exposes its error type."""
    assert sys.version_info[:2] >= (3, 14)
    assert hasattr(baml_py.errors, "BamlValidationError")


def test_baml_cli_runs():
    out = subprocess.run(
        [str(VENV_BAML_CLI), "--version"], capture_output=True, text=True
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip()


def test_typebuilder_resolves():
    from baml_client.type_builder import TypeBuilder

    assert TypeBuilder() is not None


def test_generated_client_exposes_parse_functions():
    from baml_client.sync_client import b

    assert all(hasattr(b.parse, f) for f in EXPECTED_FUNCTIONS)


def test_parse_call_signature_roundtrip():
    """Pin the canonical form: ExtractDynamic(text, baml_options={'tb': tb})."""
    from baml_client.sync_client import b
    from baml_client.type_builder import TypeBuilder

    tb = TypeBuilder()
    tb.DynamicOutput.add_property("x", tb.int())
    result = b.parse.ExtractDynamic(
        json.dumps({"x": 1}), baml_options={"tb": tb}
    )
    assert result.x == 1
