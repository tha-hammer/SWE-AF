---
date: 2026-06-11T04:27:00-04:00
author: maceo
git_commit: ebf00a3
branch: main
repository: SWE-AF
topic: "Replace SWE-AF's failing structured-output parse with BAML (parser-only, fallback-first)"
tags: [tdd, plan, baml, structured-output, swe-af, harness, parser-only]
status: implemented
implemented:
  branch: feat/baml-structured-output
  worktree: /home/maceo/Dev/SWE-AF-baml
  date: 2026-06-11
  result: "SB-1..SB-5 all green; baml-py 0.222.0 loads on py3.14; full suite 1026 passed, 1 skipped, 0 failed"
  note: "SB-5 positive case folded into SB-3 corpus (no genuine malformed-JSON capture in-repo); added real-capture negative regression on examples/pyrust/.artifacts 401 logs. Seam-safety: baml_parse_or_none swallows all exceptions (untyped list[dict] schemas like ReplanDecision are unmappable -> declines to None, never crashes)."
model_plan: /home/maceo/Dev/agentfield/thoughts/searchable/shared/plans/2026-06-07-09-04-tdd-baml-structured-output.md
tier: L1
---

# BAML Structured-Output Parser for SWE-AF — TDD Implementation Plan

## Overview

SWE-AF's "structured output handler that frequently fails" is the **agentfield
SDK's** `try_parse_from_text` — a 3-strategy regex/brace/cosmetic-repair scrape at
`agentfield/harness/_schema.py:209`. It is reached on every structured reasoner
call via `router.harness(schema=…)` → `result.parsed`. When the scrape fails it
returns `None`, and ~20+ SWE-AF reasoners then **silently degrade to hardcoded
fallbacks** (e.g. the retry advisor returns `should_retry=False`). The failure is
masked, never surfaced.

This plan replaces that parse with **BAML's Schema-Aligned Parser (SAP)**,
integrated **fallback-first** at SWE-AF's **own** wrapper layer. BAML is used
**parser-only** — it makes **no** LLM call here; it parses the raw text the CLI
harness providers (`claude_code` / `codex` / `opencode`) already emit. Each
milestone ships a **real, user-observable** capability (an importable client on
py3.14; a real schema mapped; a messy fixture the old ladder dropped now parsed; a
real reasoner returning real model content instead of a fallback). No scaffolding,
no shape-only tests.

**Scope decided:** Python `swe_af/` app only; replace the *parse*, not the model
call; fallback-first (BAML fires only when the SDK parse returns `None`, so the
happy path is byte-identical).

## Current State Analysis

This plan **diverges sharply** from the reference SDK plan
(`agentfield/…/2026-06-07-09-04-tdd-baml-structured-output.md`), because SWE-AF's
relationship to the parse code is fundamentally different. The reference plan edits
the agentfield SDK **in-source**; SWE-AF **consumes that SDK as a read-only pip
dependency** and cannot.

### Key Discoveries (verified, file:line)

- **The failing handler is a read-only dependency** —
  `.venv/lib/python3.14/site-packages/agentfield/harness/_schema.py:209`
  `try_parse_from_text(text, schema) -> Optional[Any]`: fenced-block → largest
  brace → cosmetic-repair, each `validate_against_schema` or `continue`; returns
  `None` when all three fail. SWE-AF cannot edit this file; it must intercept at
  its own layer.
- **`.parsed` population path** — `agentfield/harness/_runner.py:230-300`
  `_handle_schema_with_retry` runs `parse_and_validate` (output file) then falls
  back to `try_parse_from_text(raw.result, schema)`; `_runner.py:46
  DEFAULT_SCHEMA_RETRIES=2`, `:59 _ai_schema_repair` — all in the read-only SDK.
- **SWE-AF makes ZERO inline `agent.ai` calls** — every structured call is
  `router.harness(schema=…)` → `result.parsed` (CLI-provider path only). The
  reference plan's inline-reroute behaviors (B-A1/B-B1/B-B2) **do not map**; only
  the parser-only path applies.
- **The proven integration seam already exists** —
  `swe_af/runtime/codex_harness_patch.py:105` `apply_codex_harness_patch()`
  monkey-patches the SDK's `_schema.build_prompt_suffix`, `_runner.build_prompt_suffix`,
  `CodexProvider.execute`, and `Agent.harness`. It runs at import from
  `swe_af/reasoners/__init__.py`. This is where the BAML parse wrap belongs.
- **Binding identity — the call sites bind `_runner.try_parse_from_text`, NOT
  `_schema.try_parse_from_text`** — `_runner.py:13-21` does
  `from agentfield.harness._schema import (… try_parse_from_text)`, so `_runner` holds
  its **own** module-level reference. Every live call site uses the **bare name**:
  `_runner.py:141` (`_ai_schema_repair` fallback), `:355`
  (`_handle_schema_with_retry` initial stdout fallback), `:466` (retry stdout
  fallback). They resolve to `_runner.try_parse_from_text`. **Patching
  `_schema.try_parse_from_text` alone is a no-op for the parse path.** The existing
  patch already learned this lesson: it assigns **both** `_schema.build_prompt_suffix`
  AND `_runner.build_prompt_suffix` (`codex_harness_patch.py:297-298`). The BAML wrap
  must mirror that dual-patch, with `_runner.try_parse_from_text` as the load-bearing
  one.
- **The masked-failure pattern** — `swe_af/reasoners/execution_agents.py:168-200`:
  `result = await router.harness(…, schema=RetryAdvice, …)`; `if result.parsed is
  not None: return result.parsed.model_dump()`; else fall through to
  `RetryAdvice(should_retry=False, diagnosis="Retry advisor agent failed to
  produce a valid analysis.", …)` (`:195`). Repeated ~20+ times across
  `execution_agents.py` and `pipeline.py`.
- **Codex already reads text, not a file** — `codex_harness_patch.py:150`
  `execute_with_native_structured_output` reads `--output-last-message` back as
  `result_text`; the SDK then parses that text via the same `try_parse_from_text`
  ladder. So one parser-only swap covers codex **and** claude_code **and**
  opencode uniformly.
- **`RetryAdvice` shape (the SB-2/SB-4 demo schema)** —
  `swe_af/execution/schemas.py:381`: `should_retry: bool`, `diagnosis: str`,
  `strategy: str`, `modified_context: str`, `confidence: float = 0.5`.
- **Risk #1 — baml-py on py3.14** — `baml-py` 0.222.0 PyPI wheels are `cp38-abi3`
  (forward-compatible in principle), but **load on py3.14/linux is UNVERIFIED**
  here (no baml installed; `pip` not even on PATH in the working shell). Must be
  proven in SB-1's precondition before any codegen.

## Desired End State

Harness output that the regex ladder dropped now parses via BAML; reasoners return
**real model content** instead of hardcoded fallbacks; the happy path is unchanged.

### Observable Behaviors
- `import baml_py` succeeds on SWE-AF's py3.14 venv; `from baml_client.sync_client
  import b` exposes `b.parse.ExtractDynamic`.
- A real SWE-AF schema (`RetryAdvice`) round-trips through `pydantic_to_typebuilder`
  + BAML `b.parse` + `deserialize` to the correct typed object — deterministically,
  no network.
- A recorded messy-CLI fixture on which the SDK `try_parse_from_text` returns
  `None` parses to the correct typed object via BAML.
- The retry advisor, fed that fixture's text, returns the model's **real** advice
  (`should_retry=True` + real diagnosis), not the `should_retry=False` fallback.
- A captured real-build degraded-output fixture now produces a typed result.

## What We're NOT Doing

- **No agentfield SDK in-source edits** — it is a read-only dependency.
- **No inline `agent.ai` reroute** — SWE-AF makes none.
- **No Go SDK** — `swe_af/` is pure Python; the separate Go port is out of scope.
- **No routing model calls through BAML** — BAML is parser-only; the CLI harness
  providers still make every model call.
- **No deleting the SDK's retry knobs** (`_ai_schema_repair`, `DEFAULT_SCHEMA_RETRIES`)
  — they live in the read-only SDK; we only short-circuit by populating `.parsed`.
- **No coexistence ambiguity** — fallback-first is explicit: SDK parse first, BAML
  only on its `None`.

## BAML Integration Mechanics (design notes)

- **`baml_src/`** (committed): `generators.baml` (`output_type "python/pydantic"`,
  `default_client_mode "sync"`, `version` == installed baml-py), `clients.baml`
  (a client block referencing existing `env.ANTHROPIC_API_KEY` etc. — present only
  to satisfy `ExtractDynamic`'s `client` field; never actually called in
  parser-only mode), `functions.baml` with the load-bearing dynamic pieces:
  ```baml
  class DynamicOutput {
    @@dynamic          // no static fields; added at call time via TypeBuilder
  }
  function ExtractDynamic(prompt: string) -> DynamicOutput {
    client AnthropicClient
    prompt #"{{ prompt }} {{ ctx.output_format }}"#
  }
  ```
- **`swe_af/baml_bridge.py`** (new). Three pieces with **explicit** contracts:
  - `pydantic_to_typebuilder(model) -> TypeBuilder` — maps a runtime SWE-AF schema
    onto the `@@dynamic DynamicOutput` root via
    `tb.DynamicOutput.add_property(name, <map(field_type)>)`.
  - `deserialize(raw, model) -> M` — `raw` is a **generated `DynamicOutput` pydantic
    instance** (BAML's `output_type "python/pydantic"`), NOT a dict. Convert via
    `model.model_validate(raw.model_dump())` (the `@@dynamic`-added properties surface
    as `raw` model fields, so `raw.model_dump()` keys match the schema field names).
    Catches `pydantic.ValidationError` / `baml_py.errors.BamlValidationError` and
    **re-raises** `ValueError("Could not parse structured response: …")` on failure.
  - **Two parse helpers with deliberately different failure contracts:**
    - `baml_parse(text, schema) -> M` — `deserialize(b.parse.ExtractDynamic(text,
      baml_options={"tb": pydantic_to_typebuilder(schema)}), schema)`. **RAISES**
      `ValueError` on any failure (used by SB-2/SB-3 positive + property tests).
    - `baml_parse_or_none(text, schema) -> Optional[M]` — wraps `baml_parse` in
      `try/except (ValueError, baml_py.errors.BamlValidationError): return None`.
      **Returns `None`** on failure (used by the SB-4 seam, which must yield `None` to
      preserve the SDK's `FailureType.SCHEMA` path).
- **The seam** — `codex_harness_patch.py` is extended to wrap
  `try_parse_from_text` **fallback-first** at the binding the call sites actually use:
  capture `orig = _runner.try_parse_from_text`, install
  `wrapped = lambda text, schema: orig(text, schema) or baml_parse_or_none(text, schema)`,
  and assign it **unconditionally to BOTH** `_runner.try_parse_from_text` **and**
  `_schema.try_parse_from_text` (mirroring the `build_prompt_suffix` dual-patch at
  `codex_harness_patch.py:297-298`). `_runner.try_parse_from_text` is the load-bearing
  assignment — the bare-name call sites (`_runner.py:141,355,466`) bind it. Run the 3
  SDK strategies first; on their `None`, BAML parses exactly the inputs the regex
  ladder couldn't handle — at **one** site, shared by all providers.
- **py3.14 precondition** — SB-1 proves `import baml_py` + `baml-cli --version` +
  the API symbols (`baml_py.errors.BamlValidationError`,
  `baml_client.type_builder.TypeBuilder`, `b.parse.ExtractDynamic`) **in SWE-AF's
  `.venv`**, pinning an earlier baml-py if 0.222.0 fails to load. It also **pins the
  exact `b.parse` call signature** — `b.parse.ExtractDynamic(text,
  baml_options={"tb": tb})` (TypeBuilder passed as the `baml_options` keyword, not a
  positional dict) — with a trivial round-trip assertion, so every later milestone
  references one verified form.

## Pydantic → TypeBuilder mapping (independent oracle for `test_baml_bridge.py`)

Hand-authored ground truth the unit test asserts against (NOT derived from the
mapper's own output):

| Pydantic field type | TypeBuilder expression |
|---|---|
| `str` | `tb.string()` |
| `int` | `tb.int()` |
| `float` | `tb.float()` |
| `bool` | `tb.bool()` |
| `Optional[X]` / `X \| None` | `<map(X)>.optional()` |
| `list[X]` | `tb.list(<map(X)>)` |
| `dict[K, V]` | `tb.map(<map(K)>, <map(V)>)` |
| nested `BaseModel` `M` | `tb.add_class("M")` + `.add_property` per field, `.type()` |
| `Enum E` | `tb.add_enum("E")` + `.add_value` per member, `.type()` |
| `Literal["a","b"]` | `tb.union([tb.literal_string("a"), tb.literal_string("b")])` |
| `Union[A, B, …]` (≥2) | `tb.union([<map(A)>, <map(B)>, …])` |

Top-level fields attach to `DynamicOutput` via
`tb.DynamicOutput.add_property(field_name, <map(field_type)>)`. Unsupported
constructs (`Any`, callables) raise `TypeError` rather than silently coercing.

## Testing Strategy

- **Framework**: Python `pytest` (markers `unit`/`functional`/`integration`,
  `pytest-asyncio`), run via SWE-AF's `.venv` (`uv sync --extra dev`).
- **Deterministic, always-CI**: SB-1 (install/codegen/import on 3.14), SB-2
  (mapper via `b.parse`, LLM-free), SB-3 (fixture parse vs SDK-`None`), SB-4
  (fixture-text injected via a fake provider — no real call), SB-5 (captured
  artifact). Oracles: hand-authored expected objects, the SDK's own `None` on the
  same input, real `baml-cli` stdout.
- **Real-LLM, key-gated (optional)**: one `integration`-marked test confirms a real
  model's structured output flows end-to-end through the seam; **skipped** without
  the key, a genuine call when present. A spy/mock is never the passing oracle.
- **Property tests** (Hypothesis) where a domain exists: `deserialize(b.parse(
  json.dumps(J), tb=map(M)), M) == M(**J)` for hand-authored `(M, J)`.

---

## Behavior SB-1: baml-py loads + baml_client generates on py3.14

### Test Specification
**Given**: `baml-py` pinned in `pyproject.toml` and a minimal `baml_src/`
(`generators.baml` + `DynamicOutput`/`ExtractDynamic` + `clients.baml`).
**When**: `uv sync --extra dev` installs into `.venv` (py3.14) and
`.venv/bin/baml-cli generate` runs.
**Then**: `import baml_py` succeeds on 3.14, `.venv/bin/baml-cli --version` prints
a version, and `from baml_client.sync_client import b` exposes `b.parse.ExtractDynamic`.

**Precondition (verified, not assumed)**: before any codegen, assert *in `.venv`*:
`import baml_py` succeeds (abi3 wheel loads on 3.14), `baml-cli --version` runs,
and `baml_py.errors.BamlValidationError` + `baml_client.type_builder.TypeBuilder`
resolve. **Also pin the parse-call signature**: a trivial round-trip
`b.parse.ExtractDynamic(json.dumps({"x": 1}), baml_options={"tb": tb})` must succeed,
locking the `baml_options={"tb": …}` keyword form for all later milestones. If
0.222.0 fails to import on 3.14, pin the newest version that does and record it; the
precondition fails loudly before `baml-cli generate`.

**Version-pin ripple (single green step)**: if SB-1 pins a baml-py other than 0.222.0,
the **same** green step must (a) set `generators.baml`'s `version` to the pinned
version and (b) regenerate and commit `baml_client/**` against it — never defer to
refactor, or the committed client drifts from the installed runtime.

**Edge Cases**: missing `generators.baml` → non-zero `baml-cli` error; `.baml`
syntax error → non-zero exit with message; `baml-py` absent → precondition fails
before generate.

**Property (independent oracle)**: `EXPECTED_FUNCTIONS = ["ExtractDynamic"]`,
hand-authored; `all(hasattr(b.parse, f) for f in EXPECTED_FUNCTIONS)`. NOT
enumerated from `baml_src/` at test time.

**Files touched**: `pyproject.toml` (add `baml-py` runtime dep, pinned),
`baml_src/{generators,clients,functions}.baml`, `baml_client/**` (generated,
committed), `tests/test_baml_codegen.py`.

### TDD Cycle
🔴 **Red** — `tests/test_baml_codegen.py` asserts `from baml_client.sync_client
import b` and `hasattr(b.parse, "ExtractDynamic")`. Fails (no client).
🟢 **Green** — add pinned `baml-py` to `pyproject.toml`; `uv sync --extra dev`;
assert the precondition in `.venv` (pin-down if 0.222.0 fails to load on 3.14);
author minimal `baml_src/`; run `.venv/bin/baml-cli generate`; commit `baml_client/`.
🔵 **Refactor** — split `clients/functions/generators.baml`; assert
`generator.version` equals the installed `baml-py` version.

---

## Behavior SB-2: pydantic_to_typebuilder maps a real SWE-AF schema (deterministic)

### Test Specification
**Given**: `RetryAdvice` (`swe_af/execution/schemas.py:381`) and a hand-authored
JSON instance `J` exercising `bool`/`float`/`str` fields.
**When**: `deserialize(b.parse.ExtractDynamic(json.dumps(J), baml_options={"tb":
pydantic_to_typebuilder(RetryAdvice)}), RetryAdvice)` runs — `b.parse` makes **no**
LLM call.
**Then**: returns `RetryAdvice(**J)` with every field equal to `J`.

**Edge Cases**: nested/Optional/list/enum fields per the mapping table; unsupported
construct → `TypeError`; missing required field → `ValueError("Could not parse
structured response: …")`.

**Property**: for a model `M` and hand-authored `J`, `deserialize(b.parse.
ExtractDynamic(json.dumps(J), baml_options={"tb": pydantic_to_typebuilder(M)}), M)
== M(**J)`.

**Files touched**: `swe_af/baml_bridge.py` (new), `tests/test_baml_bridge.py` (new).

### TDD Cycle
🔴 **Red** — `test_baml_bridge.py`: `J = {"should_retry": True, "diagnosis": "x",
"strategy": "y", "modified_context": "z", "confidence": 0.8}`; assert the round-trip
equals `RetryAdvice(**J)`. The expected object is hand-authored, not derived from
the TypeBuilder's output. Fails (no module).
🟢 **Green** — implement `pydantic_to_typebuilder` (walk `model.model_fields`,
`tb.DynamicOutput.add_property` per field) + `deserialize` casting the generated
`DynamicOutput` instance via `model.model_validate(raw.model_dump())` (NOT
`model_validate(raw)` — `raw` is a foreign pydantic class), with exception
translation to `ValueError`.
🔵 **Refactor** — extend coverage to a nested model + `Optional` + `list` + `Enum`
(e.g. against `VerificationResult`/`CriterionResult`); assert `TypeError` on an
`Any`-typed field.

---

## Behavior SB-3: BAML parses messy harness output the SDK regex ladder drops

### Test Specification
**Given**: `tests/fixtures/messy_cli_output_retry_advice.txt` — a ```` ```json ````
fence with the `RetryAdvice` payload wrapped in prose, **chosen so the SDK
`try_parse_from_text` returns `None`** (e.g. malformed in a way the cosmetic-repair
ladder can't fix but SAP can, or surrounded by decoy braces).
**When**: SWE-AF's BAML parse helper parses the same text for `RetryAdvice`.
**Then**: returns the correct `RetryAdvice`, where the SDK path yielded `None`.

**Edge Cases** (two helpers, two failure contracts — see Integration Mechanics):
- `baml_parse("not json at all", schema)` → **raises** `ValueError` (assert via
  `pytest.raises(ValueError)`); `baml_parse_or_none(...)` on the same input → `None`.
- recoverable-malformed (trailing comma) → `baml_parse` returns the parsed object.
- valid embedded JSON → `baml_parse(...) == EXPECTED`.

**Property**: for any fixture whose embedded JSON validates against the schema,
`baml_parse(fixture, schema) == EXPECTED`.

**Files touched**: `swe_af/baml_bridge.py` (add `baml_parse(text, schema)` — raises —
and `baml_parse_or_none(text, schema)` — `Optional`), `tests/test_baml_parse.py`
(new), `tests/fixtures/messy_cli_output_retry_advice.txt` (new).

### TDD Cycle
🔴 **Red** — `test_baml_parse.py` feeds the fixture to `baml_parse`, asserts
`== EXPECTED`, **and** asserts the dual oracle
`agentfield.harness._schema.try_parse_from_text(fixture, RetryAdvice) is None` on
the identical input. Fails (no helper).
🟢 **Green** — implement `baml_parse(text, schema)` =
`deserialize(b.parse.ExtractDynamic(text, baml_options={"tb":
pydantic_to_typebuilder(schema)}), schema)` (raises on failure) and the thin
`baml_parse_or_none` wrapper that swallows `ValueError`/`BamlValidationError` to
`None`.
🔵 **Refactor** — add `pytest.raises(ValueError)` for `baml_parse("not json at all")`
and the matching `baml_parse_or_none(...) is None`; add malformed-recoverable→parsed;
confirm the SDK ladder still returns `None` on the recoverable case (proving BAML is
strictly stronger).

---

## Behavior SB-4: patched seam unmasks a degrading reasoner end-to-end

### Test Specification
**Given**: `codex_harness_patch.py` extended so the active `try_parse_from_text`
runs the 3 SDK strategies first, then `baml_parse_or_none` on `None`
(fallback-first), with the wrapper assigned to **`_runner.try_parse_from_text`** (the
binding the call sites at `_runner.py:141,355,466` actually invoke) **and**
`_schema.try_parse_from_text`; `apply_codex_harness_patch()` active; a fake harness
provider that returns the SB-3 fixture text.
**When**: the retry advisor (`execution_agents.py:168`) processes that harness
result — SDK-alone would give `result.parsed=None` → `should_retry=False` fallback.
**Then**: `result.parsed` is a populated `RetryAdvice` and the reasoner returns the
model's **actual** advice (`should_retry` + diagnosis from the embedded JSON), not
the fallback.

**Edge Cases**:
- SDK parse already succeeded (happy path) → BAML **not** invoked; output
  byte-identical to today.
- BAML also fails → original `None` → existing per-reasoner fallback preserved.
- non-codex providers (claude_code/opencode) get the same benefit (shared
  `try_parse_from_text`).

**Files touched**: `swe_af/runtime/codex_harness_patch.py` (wrap
`try_parse_from_text` fallback-first and assign the wrapper **unconditionally to BOTH
`_runner.try_parse_from_text` and `_schema.try_parse_from_text`** — `_runner` is the
load-bearing one, mirroring the existing `build_prompt_suffix` dual-patch at
`:297-298`), `tests/test_baml_seam_integration.py` (new).

> Blast-radius note: the wrap is **one** function at **one** site. If the diff
> starts touching individual reasoner call sites, stop — the whole point of seam
> (b) is to avoid the 20-site edit.

> Binding-identity note: assigning only `_schema.try_parse_from_text` would be a
> **no-op** — `_runner.py:13-21` imported the symbol by name, so the call sites bind
> `_runner.try_parse_from_text`. The green-step assertion must drive the `_runner`
> call path (run the retry advisor and observe `.parsed`), not merely read back a
> module attribute.

### TDD Cycle
🔴 **Red** — `test_baml_seam_integration.py`: a fake provider returns the fixture
text; call the retry advisor; assert the returned dict has `should_retry == True`
and `diagnosis != "Retry advisor agent failed to produce a valid analysis."`.
Fails (still degrades to fallback).
🟢 **Green** — extend `codex_harness_patch.py`: capture `orig =
_runner.try_parse_from_text`, install `wrapped = lambda text, schema: orig(text,
schema) or baml_parse_or_none(text, schema)`, and assign `wrapped` to **both**
`_runner.try_parse_from_text` and `_schema.try_parse_from_text` inside
`apply_codex_harness_patch()`.
🔵 **Refactor** — add the happy-path-unchanged test (provider returns a clean output
file the SDK parses → BAML wrapper observed **not** called via a spy on
`baml_parse_or_none` — patch it at the name the wrapper binds, e.g.
`codex_harness_patch.baml_parse_or_none`, not a re-imported copy) and the
BAML-also-fails test (garbage text → `result.parsed is None` → existing
`should_retry=False` fallback intact).

---

## Behavior SB-5: captured real-build regression fixture parses

### Test Specification
**Given**: `tests/fixtures/real_build_parsed_none_*.txt` — captured from an actual
SWE-AF build run whose logs showed `parsed is None → fallback` for a real reasoner
schema.
**When**: the fixture text is parsed via `baml_parse` for that schema.
**Then**: yields the correct typed object instead of `None`.

**Edge Cases**: if no real captured fixture is available, this folds into SB-3's
corpus rather than being faked; multiple captured schemas → one parametrized case
each.

**Files touched**: `tests/fixtures/real_build_parsed_none_*.txt` (new, captured),
`tests/test_baml_parse.py` (parametrize over captured fixtures).

### TDD Cycle
🔴 **Red** — parametrized case feeds each captured fixture to `baml_parse`, asserts
`== EXPECTED` (hand-verified from the run context), and asserts SDK
`try_parse_from_text` returned `None`. Fails until BAML path covers it.
🟢 **Green** — parse passes (no code change beyond SB-3/SB-4 if the seam already
covers it; otherwise extend `baml_parse` coverage).
🔵 **Refactor** — document each fixture's provenance (run id, reasoner, date) in a
header comment so the regression corpus stays auditable.

---

## Implementation Order (vertical slices)

1. **SB-1** — Python BAML codegen + py3.14 proof → *visible:* importable
   `baml_client` on 3.14; `baml-cli --version` stdout.
2. **SB-2** — `baml_bridge` mapper → *visible:* a real `RetryAdvice` object from
   JSON via BAML, deterministically.
3. **SB-3** — BAML beats the regex ladder → *visible:* fixture the SDK drops
   (`None`) now parses to a typed object.
4. **SB-4** — patched seam end-to-end → *visible:* retry advisor returns real
   model advice instead of the `should_retry=False` fallback.
5. **SB-5** — captured regression corpus → *visible:* a real production degraded
   case now produces a typed result.

## Risks & Open Items

- **baml-py on py3.14** — the #1 risk; **retired first** in SB-1 (prove
  `import baml_py` in `.venv`, else pin the newest loading version). If no baml-py
  version loads on 3.14/linux, escalate (vendor an older runtime or revisit the
  venv python) before proceeding.
- **Fallback-first preserves the happy path** — BAML only fires on the SDK's
  `None`, so already-passing parses are byte-identical (SB-4 happy-path test
  guards this).
- **Codegen determinism** — if a future drift gate is added, `baml-cli generate`
  must be deterministic; assert generate-twice → empty diff when that gate lands
  (not in scope for this plan unless requested).
- **Real-LLM test cost/flakiness** — the single integration test is key-gated and
  asserts only stably-extractable facts.
- **Monkey-patch binding identity (was the #1 review finding)** — the
  `try_parse_from_text` wrap must be installed in `apply_codex_harness_patch()` (which
  already runs at `reasoners/__init__` import) and assigned to **`_runner.try_parse_from_text`**,
  because `_runner.py:13-21` imported the symbol by name and the call sites
  (`_runner.py:141,355,466`) bind that local reference — patching `_schema.` alone is
  a no-op. Assign to both for symmetry, mirroring the established
  `build_prompt_suffix` dual-patch (`codex_harness_patch.py:297-298`). SB-4's green
  step verifies the live `_runner` call path, not just the module attribute.

## References

- Model plan (agentfield SDK): `/home/maceo/Dev/agentfield/thoughts/searchable/shared/plans/2026-06-07-09-04-tdd-baml-structured-output.md`
- Failing handler: `agentfield/harness/_schema.py:209` (`try_parse_from_text`),
  population at `_runner.py:230-300` (read-only pip dep, py3.14 site-packages)
- Seam: `swe_af/runtime/codex_harness_patch.py:105,150,272-301`
- Masked-fallback pattern: `swe_af/reasoners/execution_agents.py:168-200`
- Demo schema: `swe_af/execution/schemas.py:381` (`RetryAdvice`)
- BAML symbols verified in the model plan against `baml-py==0.222.0`
  (TypeBuilder, `b.parse.Fn`, `baml_py.errors.BamlValidationError`)
