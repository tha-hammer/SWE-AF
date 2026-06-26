# tech_lead REJECT-first behavioral eval (SWE-AF-292, Phase 2)

A seeded-flaw architecture the tech_lead gate **must reject**. Two unambiguous,
independent defects:

1. **Internal-consistency contradiction + unmet AC2** — the PRD requires
   structured errors (`code` / `field` / `line` / `column`); the architecture
   models errors as plain strings (`errors: list[str]`). The criterion has no
   implementation path and the two documents contradict.
2. **Unmet AC3 (no traceability path)** — the PRD requires pagination (>50
   problems → first 50 + `next_page`); the architecture returns every problem in
   one list with no pagination.

A reviewer that maps each acceptance criterion to a concrete path cannot approve
this. The RED→GREEN proof:

- **RED (baseline, APPROVE-first prompt)** — the pre-Phase-2 tech_lead leads its
  decision framework with "APPROVE when…"; first-token framing on a rejection
  gate tends to rubber-stamp this flaw (`approved == true`).
- **GREEN (Phase 2, REJECT-first prompt)** — the reframed prompt defaults to
  REJECT and enumerates the reject criteria first; it rejects this fixture
  (`approved == false`) and names the two defects in `feedback`.

## Running the eval (node-driven — local pytest cannot drive the live harness)

`run_tech_lead` reads `prd.md` + `architecture.md` from
`{repo_path}/{artifacts_dir}/plan/`. Stage this fixture into a repo reachable by a
build node, then invoke the reasoner:

```bash
# stage the fixture
mkdir -p ~/Dev/_tech-lead-eval/.artifacts/plan
cp tests/fixtures/prompt_evals/tech_lead/{prd.md,architecture.md} \
   ~/Dev/_tech-lead-eval/.artifacts/plan/

# run on a node whose image carries the prompt under test
curl -s -X POST http://localhost:8080/api/v1/execute/async/swe-planner.run_tech_lead \
  -H 'Content-Type: application/json' -d '{"input":{
    "prd": {},
    "repo_path": "/workspaces/dev/_tech-lead-eval",
    "artifacts_dir": ".artifacts",
    "ai_provider": "claude",
    "model": "sonnet"
  }}'
# poll GET /api/v1/executions/<exec_id>; read result.approved (expect false for GREEN)
```

The **baseline (RED)** runs against the current node image (committed APPROVE-first
prompt). The **GREEN** run requires the `feat/planning-prompt-enhancement` prompt
in a node image (rebuild) — folded into Phase 5 end-to-end verification
(SWE-AF-bbh) unless run sooner.
