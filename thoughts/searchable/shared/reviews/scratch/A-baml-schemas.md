# Citation Verification — BAML schemas (Reviewer A)

Worktree: `/home/maceo/Dev/SWE-AF-baml` @ `6517b17` (branch `feat/baml-structured-output`).
Method: Read/Grep only, no modifications. Quotes are verbatim from the cited files.

---

## Claim 1 — `swe_af/baml_bridge.py:70-72` — `_map_type` handles `list[X]`

**Verdict: ACCURATE.**

Lines 69-72:
```python
69	    # list[X]
70	    if origin in (list, typing.List):
71	        (inner,) = get_args(annotation) or (Any,)
72	        return tb.list(_map_type(inner, tb))
```
The `list[X]` branch is exactly at 70-72 (with the comment on 69). Recurses on the element type and wraps in `tb.list(...)`. Anchor is correct.

---

## Claim 2 — `swe_af/baml_bridge.py:108-112` — `_map_type` handles nested `BaseModel`

**Verdict: ACCURATE.**

Lines 107-112:
```python
107	    # nested BaseModel M
108	    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
109	        cb = tb.add_class(annotation.__name__)
110	        for fname, finfo in annotation.model_fields.items():
111	            cb.add_property(fname, _field_type(finfo, tb))
112	        return cb.type()
```
Nested-`BaseModel` branch is exactly at 108-112. Creates a dynamic class, adds each field via `_field_type`, returns `cb.type()`. Anchor is correct.

---

## Claim 3 — `swe_af/baml_bridge.py:169-196` — `baml_parse` raises; `baml_parse_or_none` declines to `None`

**Verdict: ACCURATE.**

- `baml_parse` def at **169**; raises `ValueError` (line 180) and via `deserialize` (165-166):
```python
169	def baml_parse(text: str, schema: type[M]) -> M:
...
179	    except baml_py.errors.BamlError as exc:
180	        raise ValueError(f"Could not parse structured response: {exc}") from exc
181	    return deserialize(raw, schema)
```
- `baml_parse_or_none` def at **184**, returns `None` on ANY exception (193-196):
```python
184	def baml_parse_or_none(text: str, schema: type[M]) -> Optional[M]:
...
193	        return baml_parse(text, schema)
194	    except Exception:
195	        return None
```
Range 169-196 covers both helpers and their respective failure contracts. Anchor is correct.

---

## Claim 4 — `baml_parse_or_none` fires ONLY on the agentfield SDK returning `None` (fallback-first). Gating + call sites.

**Verdict: ACCURATE (gating confirmed).**

Call site is `swe_af/runtime/codex_harness_patch.py`, function `try_parse_from_text_fallback_first` (lines 301-309):
```python
301	    def try_parse_from_text_fallback_first(text: Any, schema: Any) -> Any:
302	        result = _ORIGINAL_TRY_PARSE_FROM_TEXT(text, schema)
303	        if result is not None:
304	            return result
305	        # Module-global lookup at call time so tests can spy on
306	        # codex_harness_patch.baml_parse_or_none (the bound name used here).
307	        if baml_parse_or_none is None:
308	            return None
309	        return baml_parse_or_none(text, schema)
```
The SDK's original `try_parse_from_text` runs FIRST (302). If it returns non-`None`, BAML is never invoked (303-304 early return). BAML's `baml_parse_or_none` is only reached when the SDK yields `None` — fallback-first is exactly as claimed. There is also an import-guard at 16-18 binding `baml_parse_or_none = None` if the bridge import fails, and 307-308 short-circuits to `None` in that case.

Usage grep across `swe_af/`:
- `swe_af/baml_bridge.py` — definitions + `__all__` exports (lines 9, 10, 169, 184, 194, 202, 203).
- `swe_af/runtime/codex_harness_patch.py` — import at 16, guard at 18, only call at 309 (refs in comments at 12, 306, 307).

No other production callers. `baml_parse` (the raising variant) has NO production call site outside the bridge itself — it is only exercised by `tests/test_baml_bridge.py`. (Worth flagging: the only consumer of the bridge is the codex_harness_patch seam via the `_or_none` variant.)

---

## Claim 5 — `pydantic_to_typebuilder` exists; Behavior 1 wants to attach a BAML `@check`. Real name/signature + whether `add_property()` exposes `.description()` but NOT `.assert_()`.

**Verdict: ACCURATE on the function; ACCURATE+CRITICAL on the API gap.**

Real function (verbatim, `swe_af/baml_bridge.py:132-137`):
```python
132	def pydantic_to_typebuilder(model: type[BaseModel]) -> TypeBuilder:
133	    """Build a fresh TypeBuilder whose @@dynamic DynamicOutput root mirrors *model*."""
134	    tb = TypeBuilder()
135	    for fname, finfo in model.model_fields.items():
136	        tb.DynamicOutput.add_property(fname, _field_type(finfo, tb))
137	    return tb
```
Name/signature confirmed: `pydantic_to_typebuilder(model: type[BaseModel]) -> TypeBuilder`. It builds a fresh `TypeBuilder`, iterates `model.model_fields`, and attaches each field to the `@@dynamic DynamicOutput` root via `tb.DynamicOutput.add_property(name, type)`. Nested models go through `_map_type`'s BaseModel branch (`tb.add_class(...).add_property(...)`).

**BAML add_property API (the wrapper `baml_py`, py3.14):**
`add_property` returns a `ClassPropertyBuilder` (`.venv/lib/python3.14/site-packages/baml_py/type_builder.py:130-144`):
```python
130	    def add_property(self, name: str, type: FieldType) -> "ClassPropertyBuilder":
131	        return ClassPropertyBuilder(self.__bldr.property(name).type(type))
...
134	class ClassPropertyBuilder:
138	    def alias(self, alias): ...
142	    def description(self, description): ...
```
`ClassPropertyBuilder` exposes ONLY `.alias()` and `.description()` — **no `.assert_()`, `.check()`, or `.constraint()`**. Confirmed against the native stub `baml_py.pyi:537-541`:
```
537	class ClassPropertyBuilder:
540	    def alias(self, alias: Optional[str]) -> ClassPropertyBuilder: ...
541	    def description(self, description: Optional[str]) -> ClassPropertyBuilder: ...
```
`FieldType` (`type_builder.py` ~40-113 and `.pyi:515`) likewise has NO constraint/assert/check method — only `string/int/float/bool/list/map/union/null/literal_*/add_class/add_enum/add_baml`.

**INTERFACE GAP (flag):** Behavior 1's premise — "extend `pydantic_to_typebuilder` to attach a BAML `@check`" — has NO runtime-TypeBuilder API to hang it on. The dynamic builder cannot express `@check`/`@assert` via `add_property(...).<something>()`. The ONLY escape hatch is `TypeBuilder.add_baml(baml_str)` (`type_builder.py:110`, native `baml_py.pyi:333 add_baml(self, baml, rt)`), which injects raw BAML source — i.e. constraints would have to be written as a raw BAML string, not via the fluent property builder. Any plan step that says ".assert_()" or "add a @check through add_property" is calling a method that does not exist.

---

## Claim 6 — `swe_af/reasoners/schemas.py` `PlannedIssue`: insert `AcceptanceCheck` "before line 78", add `verification: list[AcceptanceCheck] = []` "at 92/93 grouped with guidance".

**Verdict: DRIFTED (insertion points are off but salvageable).**

Actual anchors:
- `class PlannedIssue(BaseModel):` starts at **line 78** (claim's "before line 78" insertion point is correct — `AcceptanceCheck` would slot in the blank lines 76-77, immediately before `PlannedIssue`). **ACCURATE** for the AcceptanceCheck insertion.
- `guidance` field is at **line 92**:
```python
92	    guidance: IssueGuidance | None = None  # Per-issue guidance from sprint planner
```
- The plan's "add `verification` at line 92/93 grouped with guidance" is **DRIFTED**: line 92 is *occupied* by `guidance`; line 93 is `target_repo`:
```python
91	    sequence_number: int | None = None  # ...
92	    guidance: IssueGuidance | None = None  # ...
93	    target_repo: str = ""  # Target repository for multi-repo builds ...
```
  Inserting "at line 92/93" as written would split `guidance` (92) from `target_repo` (93). The correct insertion is **a new line immediately after 92 (i.e. before `target_repo` at 93)** so it reads guidance → verification → target_repo. Corrected anchor: **insert after line 92**, not "at 92/93".

Full `PlannedIssue` field list (lines 81-93), with types:
| field | type | default |
|-------|------|---------|
| `name` | `str` | (required) |
| `title` | `str` | (required) |
| `description` | `str` | (required) |
| `acceptance_criteria` | `list[str]` | (required) |
| `depends_on` | `list[str]` | `[]` |
| `provides` | `list[str]` | `[]` |
| `estimated_complexity` | `str` | `"medium"` |
| `files_to_create` | `list[str]` | `[]` |
| `files_to_modify` | `list[str]` | `[]` |
| `testing_strategy` | `str` | `""` |
| `sequence_number` | `int \| None` | `None` |
| `guidance` | `IssueGuidance \| None` | `None` |
| `target_repo` | `str` | `""` |

Note: there are 13 fields. `class PlanResult` starts at line 96. Inserting `AcceptanceCheck` before 78 pushes every line down by N, so the "92/93" anchor will drift further once AcceptanceCheck is added above. The plan should express both insertions relative to *named anchors* (before `class PlannedIssue` / after the `guidance` field) rather than absolute line numbers.

---

## Claim 7 — `tests/test_baml_bridge.py:26-32` `_roundtrip` helper. Quote + exact signature.

**Verdict: ACCURATE.**

Lines 26-32:
```python
26	def _roundtrip(model, instance_json):
27	    """parse(json.dumps(J)) via the mapped TypeBuilder, then cast back to model."""
28	    raw = b.parse.ExtractDynamic(
29	        json.dumps(instance_json),
30	        baml_options={"tb": pydantic_to_typebuilder(model)},
31	    )
32	    return deserialize(raw, model)
```
Signature: `_roundtrip(model, instance_json)` — two positional args, no type hints, no defaults. Body calls `b.parse.ExtractDynamic(json.dumps(instance_json), baml_options={"tb": pydantic_to_typebuilder(model)})` then `deserialize(raw, model)`. The plan's "copy the `_roundtrip` helper" instruction is grounded; note the helper depends on module imports `b` (from `baml_client.sync_client`), `json`, `pydantic_to_typebuilder`, and `deserialize`.

---

## Claim 8 — `baml_src/functions.baml` exists; `ExtractDynamic` / `@@dynamic DynamicOutput`.

**Verdict: ACCURATE.**

`baml_src/functions.baml` exists (alongside `clients.baml`, `generators.baml`). Full content:
```baml
class DynamicOutput {
  @@dynamic
}

function ExtractDynamic(prompt: string) -> DynamicOutput {
  client AnthropicClient
  prompt #"
    {{ prompt }}

    {{ ctx.output_format }}
  "#
}
```
`DynamicOutput` is a class with NO static fields, only `@@dynamic` (shape supplied at call time by the TypeBuilder). `ExtractDynamic(prompt: string) -> DynamicOutput` uses `client AnthropicClient` and a prompt that echoes `{{ prompt }}` + `{{ ctx.output_format }}`. Matches Behavior 0's spike reference. (Note: the client `AnthropicClient` is defined in `clients.baml`, present only to satisfy the required `client` field; `b.parse.*` makes no network call.)

---

## Claim 9 — Does `AcceptanceCheck` already exist? Does `verification` exist as a field on any schema?

**Verdict: WRONG / NON-EXISTENT (both are net-new — confirms the plan adds them fresh).**

- `AcceptanceCheck`: grep across `**/*.py` and `**/*.baml` returns **zero hits**. The type does not exist anywhere — the plan must create it. No collision.
- `verification` as a field: grep for `verification` across `swe_af/**/*.py` returns **zero hits**. (Note: `VerificationResult` and `verify_fix`-style names exist elsewhere in `swe_af/execution/schemas.py`, but no field literally named `verification` on any pydantic schema.) No collision on `PlannedIssue.verification`.

This is consistent with the plan introducing both `AcceptanceCheck` and `PlannedIssue.verification` as new constructs.

---

## Cross-cutting flags

1. **(Claim 5) Missing API — HIGH.** Behavior 1 assumes a `@check`/`.assert_()` path on the dynamic property builder. No such method exists; `ClassPropertyBuilder` only has `alias`/`description`. Runtime constraints would have to go through `TypeBuilder.add_baml(raw_baml_str)`. The plan's refactor of `pydantic_to_typebuilder` to "attach a BAML @check" needs to be re-scoped to raw-BAML injection, or the constraint must be enforced in pydantic/`deserialize` instead of at the SAP layer.
2. **(Claim 6) Absolute line anchors drift.** Adding `AcceptanceCheck` before line 78 shifts all subsequent lines; the "92/93" anchor for `verification` is already imprecise (92 is occupied by `guidance`; correct is *after* 92, before `target_repo` at 93). Use named anchors.
3. **(Claim 4) Single consumer.** `baml_parse` (raising) has no production caller; only `baml_parse_or_none` is wired, via the codex_harness_patch fallback-first seam. Any Behavior that wants to surface BAML parse *errors* (rather than silent decline) currently has no production entry point.
