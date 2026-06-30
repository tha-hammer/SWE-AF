---
date: 2026-06-11
reviewer: claude (review_plan)
plan: 2026-06-11-04-27-tdd-baml-structured-output-swe-af.md
git_commit: ebf00a3
status: needs-minor-revision
verdict: 1 critical (anticipated, must be made unconditional), 3 moderate, 2 minor
---

# Plan Review Report: BAML Structured-Output Parser for SWE-AF

All five load-bearing file:line claims in the plan were verified against the actual
tree (incl. the read-only SDK in `.venv/lib/python3.14/site-packages/agentfield/`).
The plan is unusually well-grounded — schema fields, fallback site, the 3-strategy
parser body, the `~20+` fallback count, and the seam location all check out. One
**critical** binding-identity issue makes the SB-4 seam patch as primarily written
a no-op; the plan *anticipates* it but phrases it conditionally. Fix that, clarify
three contracts, and it's ready.

### Review Summary
| Category | Status | Issues Found |
|----------|--------|--------------|
| Contracts | ⚠️ | 1 critical, 1 moderate |
| Interfaces | ⚠️ | 1 moderate |
| Promises | ✅ | 0 |
| Data Models | ⚠️ | 1 moderate |
| APIs | ✅ | 0 (parser-only; no new HTTP surface) |

---

### Verified Claims (independent confirmation)

- ✅ `try_parse_from_text(text, schema) -> Optional[Any]` at `_schema.py:209`; 3
  strategies (fenced → largest brace → cosmetic repair), each `continue` on failure,
  implicit `return None`. **Exact** as described.
- ✅ `.parsed` population path: `_runner._handle_schema_with_retry` runs
  `parse_and_validate(output_path)` (`:348`) then `try_parse_from_text(initial_raw.result)`
  (`:355`); `DEFAULT_SCHEMA_RETRIES=2` (`:46`), `_ai_schema_repair` (`:59`). **Exact.**
- ✅ Masked fallback: `execution_agents.py:184` `if result.parsed is not None: return
  result.parsed.model_dump()`; else `:196` `RetryAdvice(should_retry=False,
  diagnosis="Retry advisor agent failed to produce a valid analysis.", …).model_dump()`.
  SB-4's asserted contract (`should_retry == True`, `diagnosis !=` that string) is
  **accurate**.
- ✅ `RetryAdvice` fields `should_retry: bool, diagnosis: str, strategy: str,
  modified_context: str, confidence: float = 0.5` at `schemas.py:381`. **Exact.**
- ✅ Fallback frequency: 23 `.parsed is (not) None` checks across `reasoners/` +
  `execution/`. Plan's "~20+" — **accurate**.
- ✅ Seam precedent: `codex_harness_patch.py` already wraps `_schema.build_prompt_suffix`
  AND `CodexProvider.execute`/`Agent.harness`; runs at `reasoners/__init__` import. Real.

---

### Contract Review

#### ❌ CRITICAL — the seam patches the wrong binding (SB-4)
The plan's SB-4 *green* step says: install the wrapper and "assign to
`_schema.try_parse_from_text` (and any direct `_runner` reference)". The design
notes (lines 138-144) speak only of wrapping "the SDK's `try_parse_from_text`". The
`_runner` patch is framed as conditional ("**if** it imports the symbol directly").

It **does** import it directly. `_runner.py:13-21`:
```python
from agentfield.harness._schema import (..., try_parse_from_text)
```
Every live call site — `_runner.py:141`, `:355`, `:466` — uses the **bare name**,
which resolves to `_runner`'s own module-level binding `_runner.try_parse_from_text`,
NOT `_schema.try_parse_from_text`. Therefore:

- Patching `_schema.try_parse_from_text` **alone has zero effect** on the runner path
  that actually populates `.parsed`. SB-4 would either fail to unmask the reasoner,
  or (worse) go green only because the test reaches a different path than production.
- The **load-bearing** patch is `_runner.try_parse_from_text = wrapped`. It is not
  optional — it is the whole mechanism.

**Precedent already in the file:** `apply_codex_harness_patch()` patches BOTH
`_schema.build_prompt_suffix = …` AND `_runner.build_prompt_suffix = …`
(`codex_harness_patch.py:297-298`) for exactly this binding-identity reason. SB-4
should mirror that pattern verbatim.

> Recommendation: rewrite SB-4 to make `_runner.try_parse_from_text` the **primary,
> unconditional** patch (patch `_schema.` too for completeness/symmetry, but state
> that `_runner` is the one the call sites bind). SB-4's green-step verification must
> assert the patch is observed *at the call site* (`_runner` path), not just that a
> module attribute changed — the plan's own Risk note already demands this; make the
> test enforce it.

#### ⚠️ MODERATE — `baml_parse` return contract contradicts SB-3 edge case
`deserialize(raw, model)` is specified to catch `ValidationError`/`BamlValidationError`
and **re-raise** `ValueError("Could not parse structured response: …")`. SB-3 defines
`baml_parse(text, schema) = deserialize(b.parse.ExtractDynamic(text, …), schema)` —
so `baml_parse` **raises** on failure. But SB-3 *Edge Cases* assert
`baml_parse("not json at all") → None`. A function cannot both raise ValueError and
return None on the same input.

> Recommendation: define two explicit contracts and use the right one per site:
> - `baml_parse(text, schema) -> M` — **raises** `ValueError` on failure (SB-2/SB-3
>   positive assertions, property tests).
> - `baml_parse_or_none(text, schema) -> Optional[M]` — swallows to `None` (the SB-4
>   seam, which must return `None` to preserve the `FailureType.SCHEMA` path).
>
> Then fix SB-3's "unparseable → None" edge to either target `baml_parse_or_none`, or
> assert `pytest.raises(ValueError)` against `baml_parse`. The seam's
> `orig(...) or baml_parse_or_none(...)` form (SB-4 green) is correct and should be
> the canonical one.

---

### Interface Review

#### ⚠️ MODERATE — `b.parse.ExtractDynamic` call signature is inconsistent
Three different call forms appear:
- SB-2 *When*: `b.parse.ExtractDynamic(json.dumps(J), baml_options={"tb": …})`
- SB-2 *Property* & design notes: `b.parse.ExtractDynamic(text, {"tb": …})` (positional)

In `baml-py`, the TypeBuilder is passed via the `baml_options={"tb": …}` keyword; the
bare positional dict is almost certainly wrong. This is unverified on py3.14 anyway.

> Recommendation: SB-1's precondition already resolves API symbols
> (`TypeBuilder`, `b.parse.ExtractDynamic`, `BamlValidationError`) in `.venv`. **Add
> one assertion** that pins the exact parse-call signature (a trivial round-trip on a
> known JSON), and normalize every later reference in the plan to that one form. This
> retires the second-biggest API unknown alongside the py3.14 load risk.

---

### Promise Review

#### ✅ Well-defined
- Fallback-first / happy-path byte-identical: BAML fires only on the SDK's `None`;
  guarded by the SB-4 happy-path "spy observes `baml_parse` NOT called" test. Sound.
- Parser-only / no LLM call: `b.parse.*` is the SAP parse entry, no network. The
  `clients.baml`/`ANTHROPIC_API_KEY` block is explicitly present only to satisfy the
  `client` field and never invoked. Clear.
- Monkey-patch ordering: installed inside `apply_codex_harness_patch()`, already run
  at `reasoners/__init__` import. Correct location.

(The one promise gap — "patch the symbol the call sites actually bind" — is captured
as the CRITICAL contract issue above, not double-counted here.)

---

### Data Model Review

#### ⚠️ MODERATE — `DynamicOutput → pydantic model` conversion underspecified
`deserialize` is described as casting BAML's `DynamicOutput` to a model via
`model.model_validate(raw)`. With `output_type "python/pydantic"`, BAML returns a
**generated `DynamicOutput` pydantic instance**, not a dict. `RetryAdvice.model_validate(<a
DynamicOutput instance>)` will not accept a foreign model class unless via
`from_attributes=True` or a dump. The conversion bridge is the crux of SB-2's green
step and is left implicit.

> Recommendation: specify the exact bridge, e.g.
> `model.model_validate(raw.model_dump())` (or `model(**raw.model_dump())`), and add a
> one-line note that `@@dynamic`-added properties surface on `raw` as model fields /
> dump keys. SB-2's hand-authored oracle (`== RetryAdvice(**J)`) only holds if the
> dump keys match `J` exactly — make that the assertion.

#### ✅ Well-defined
- The Pydantic→TypeBuilder mapping table (lines 155-167) is a genuine **independent
  oracle** (hand-authored, not derived from the mapper). Good TDD hygiene.
- `Unsupported (Any/callable) → TypeError` is an explicit, testable contract.

---

### API Review
✅ No new external API surface. BAML is parser-only; the CLI harness providers
(`claude_code`/`codex`/`opencode`) still own every model call. The `b.parse` "API" is
the only new interface and is covered under Interface Review above.

---

### Minor Issues

- ⚠️ **SB-1 version-pin ripple.** If `baml-py==0.222.0` fails to load on py3.14 and a
  different version is pinned, `generators.baml`'s `version` field AND the committed
  `baml_client/**` must regenerate to match in the **same** green step (not deferred
  to refactor). State this explicitly so a pin-down can't leave a stale generated
  client.
- ⚠️ **SB-4 spy binding identity.** The "happy path — BAML not called" refactor test
  spies on `baml_parse`. The spy must target the **same bound name** the wrapper
  invokes (same lesson as the critical issue) or it will silently never trip. Note it.

---

### Critical Issues (Must Address Before Implementation)

1. **Seam binds `_schema.try_parse_from_text` but the call sites bind
   `_runner.try_parse_from_text`** (SB-4).
   - Impact: the unmask never happens in production / SB-4 green is misleading.
   - Fix: make `_runner.try_parse_from_text = wrapped` the primary, unconditional
     patch, mirroring the existing `build_prompt_suffix` dual-patch at
     `codex_harness_patch.py:297-298`; assert at the call site in the green step.

### Suggested Plan Amendments
```diff
# SB-4 green
- install a wrapper that returns `orig(text, schema) or baml_parse_or_none(...)`;
- assign to `_schema.try_parse_from_text` (and any direct `_runner` reference)
+ capture orig = _runner.try_parse_from_text; install wrapper
+   `lambda text, schema: orig(text, schema) or baml_parse_or_none(text, schema)`;
+ assign UNCONDITIONALLY to BOTH `_runner.try_parse_from_text` and
+   `_schema.try_parse_from_text` (mirror the build_prompt_suffix dual-patch at
+   codex_harness_patch.py:297-298). Green-step assertion must drive the `_runner`
+   call path, not just read back the module attribute.

# SB-3 + bridge contracts
+ Define baml_parse(...) -> M (RAISES ValueError on failure) vs
+   baml_parse_or_none(...) -> Optional[M] (None on failure; used by the seam).
+ Fix SB-3 "unparseable → None" edge to target baml_parse_or_none (or expect raises).

# SB-2 / baml_bridge
+ Specify deserialize bridge: model.model_validate(raw.model_dump()) — raw is a
+   generated DynamicOutput pydantic instance, not a dict.

# SB-1 precondition
+ Pin the exact b.parse.ExtractDynamic call signature (baml_options={"tb": ...})
+   with a round-trip assertion; normalize all later references to it.
```

### Approval Status
- [ ] Ready for Implementation
- [x] **Needs Minor Revision** — one critical (already anticipated; make the
      `_runner` patch unconditional and verified at the call site) + three moderate
      contract clarifications. No rework of the architecture; the seam strategy,
      scope boundaries, and oracles are sound.
- [ ] Needs Major Revision
