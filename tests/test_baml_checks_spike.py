"""Behavior 0 spike: can a BAML ``@check``/``@assert`` ride a ``@@dynamic`` field?

Risk-retirement spike. **Not load-bearing** — the plan guarantees command
validity with a Pydantic validator (Behavior 1) regardless of this outcome. The
deliverable is a recorded verdict: does a check attached to the runtime-built
``DynamicOutput`` root surface on the parsed result, or is it rejected/ignored?

API note (verified in ``baml_py.pyi``): there is **no** fluent ``@check``/
``@assert`` builder for dynamic fields — ``tb.add_property()`` returns a
``ClassPropertyBuilder`` exposing only ``.alias()`` / ``.description()``. The only
attach mechanism is ``tb.add_baml(<raw baml string>)``; this spike exercises
exactly that.

VERDICT (observed 2026-06-11, branch venv, baml_py 0.222.0): **outcome (a)** —
a ``@check`` DOES ride a ``@@dynamic`` field. ``tb.add_baml("dynamic class
DynamicOutput { command string @check(nonempty, {{ this|length > 0 }}) }")`` is
accepted, and ``b.parse.ExtractDynamic`` returns ``command`` as a **dict-shaped
Checked value**::

    {'value': '', 'checks': {'nonempty': {'name': 'nonempty',
                                          'expression': 'this|length > 0',
                                          'status': 'failed'}}}

readable as ``raw.command["checks"]["nonempty"]["status"]`` ("failed" for an
empty command, "succeeded" for a non-empty one).

**Consequence for Behavior 1:** the optional BAML ``@check`` echo is *feasible*
but **non-load-bearing**, for an independent reason — the bridge is
fallback-first (``baml_parse_or_none`` fires only on the SDK's ``None``), so on
the happy path the check never runs. The always-on validity guarantee must
therefore live in Pydantic (``@field_validator``), which runs on every parse. The
BAML echo would only ever fire on the fallback path and nothing reads its dict
status, so Behavior 1 relies on the Pydantic validator and treats the BAML echo
as a documented, un-wired option.
"""

import pytest

from baml_client.sync_client import b
from baml_client.type_builder import TypeBuilder

pytestmark = pytest.mark.unit

# A @check on the @@dynamic root, attached via the only available mechanism.
_CHECK_BAML = (
    "dynamic class DynamicOutput {\n"
    "  command string @check(nonempty, {{ this|length > 0 }})\n"
    "}"
)


def _build_with_check() -> TypeBuilder:
    tb = TypeBuilder()
    tb.add_baml(_CHECK_BAML)
    return tb


def test_check_on_dynamic_field_surfaces_failed_status():
    """Green: outcome (a) — a failing @check on command="" surfaces as a dict."""
    tb = _build_with_check()  # add_baml does not raise on a @check'd dynamic field
    raw = b.parse.ExtractDynamic('{"command": ""}', baml_options={"tb": tb})

    # The Checked value surfaces as a dict: {"value": ..., "checks": {...}}.
    assert isinstance(raw.command, dict)
    assert raw.command["value"] == ""
    assert raw.command["checks"]["nonempty"]["status"] == "failed"


def test_check_on_dynamic_field_surfaces_succeeded_status():
    """Outcome (a), positive case — a non-empty command passes the same check."""
    tb = _build_with_check()
    raw = b.parse.ExtractDynamic('{"command": "pytest -k lexer"}', baml_options={"tb": tb})

    assert raw.command["value"] == "pytest -k lexer"
    assert raw.command["checks"]["nonempty"]["status"] == "succeeded"
