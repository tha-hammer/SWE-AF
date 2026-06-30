---
title: CV graph → React Flow + seed Railway dev
task: Seed Railway dev env + swap graph to ApexCharts
slug: cv-graph-reactflow
effort: E3
phase: complete
progress: 34/34
mode: ALGORITHM
started: 2026-06-26
updated: 2026-06-26
---

## Context

Two-part request resumed from handoff `2026-06-26_15-25-00_contract-view-functional-verification.md`:

1. **Seed the Railway DEVELOPMENT environment** (NOT prod) with the contract-explode demo
   data so the deployed dev Exploded Contract View shows data.
2. **Swap the contract dependency graph to a "better renderer."** User named ApexCharts
   (Metronic React stack). **BLOCKING FINDING:** ApexCharts has 23 chart types and NONE is a
   node-link/force-directed/network graph — it cannot render this graph. User chose
   **React Flow (@xyflow/react)** as the replacement (keeps nodes+edges+blast-radius, fixes
   the cut-off framing, fits Metronic/Tailwind). `apexcharts` is already installed (unused for
   this graph).

Work happens in a clean worktree `/home/maceo/Dev/cosmic-HR04-cv-reactflow` (branch
`cv-graph-reactflow`, off `origin/cosmic-HR04` @ efb3db98 = #44).

Component contract to PRESERVE: `ExplodedCanvas({ nodes, edges, overlays, selectedNodeId,
onNodeSelect })`, `data-testid="exploded-canvas"`, node click → `onNodeSelect(id)`, cost
overlay when `overlays.has('cost')`, selection highlight, dangling-edge filter, registry-driven
node shapes (node-types.json: rect/circle/diamond/hexagon + colorToken) and edge styles
(edge-types.json: solid/dashed/dashed-double + colorToken).

Seed facts: dev Postgres public URL `trolley.proxy.rlwy.net:24846/railway` (via railway CLI,
env `development`, ID 3cc71631 — handoff mislabeled it "prod"). Contract tables present
(064/065 applied). Target org `cosmicinc` = `6a6a0732-e2ac-4991-a2a1-67c53a6484f9`. Seed script
`scripts/seed-contract-explode-demo.cjs` is idempotent, needs `DATABASE_URL` + `SEED_ORG_ID` + `pg`.

### Risks
- React Flow needs ResizeObserver + sized parent; in jsdom (vitest) tests may need a
  ResizeObserver mock and won't measure real sizes. Mitigation: assert on testid container,
  add RO polyfill if missing.
- Seeding wrong org → deployed dev view stays dark. Mitigation: target `cosmicinc` (user's org);
  seed is idempotent so re-target is cheap.
- d3-force static layout must finish before handing positions to React Flow (no live tick).
- Must not delete/skip the 12 existing unit tests (repo test-integrity ethos + steering rule).

### Plan
- Add `@xyflow/react` to recruiter-ui deps; import its CSS.
- Rewrite `ExplodedCanvas.jsx`: compute node positions with a static d3-force sim, render with
  `<ReactFlow>` (custom node type reading node-types.json; edges styled from edge-types.json;
  `fitView`; `onNodeClick`→onNodeSelect; cost overlay; selection ring; dangling filter).
- Adapt `ExplodedCanvas.test.jsx` assertions to React Flow DOM (keep all 12 cases).
- Run seed against dev DB under cosmicinc; verify rows.
- Verify: install deps, lint/build recruiter-ui, run the unit test file, /simplify the diff.

## Criteria

- [x] ISC-1: `@xyflow/react` added to recruiter-ui/package.json dependencies
- [x] ISC-2: `@xyflow/react/dist/style.css` imported by the canvas component
- [x] ISC-3: ExplodedCanvas renders `<ReactFlow>` (no d3 SVG hand-render remains)
- [x] ISC-4: Component still exports named `ExplodedCanvas` with identical prop signature
- [x] ISC-5: Wrapper keeps `data-testid="exploded-canvas"`
- [x] ISC-6: Node positions computed via static d3-force simulation
- [x] ISC-7: `contract` kind renders rect shape with its colorToken
- [x] ISC-8: `vendor` kind renders rect shape with its colorToken
- [x] ISC-9: `system` kind renders circle shape with its colorToken
- [x] ISC-10: `team` kind renders hexagon shape with its colorToken
- [x] ISC-11: `cost_center` kind renders diamond shape with its colorToken
- [x] ISC-12: `person` kind renders circle shape with its colorToken
- [x] ISC-13: `project` kind renders rect shape with its colorToken
- [x] ISC-14: Unknown kind falls back to `system` config (no crash)
- [x] ISC-15: Node label text rendered for each node
- [x] ISC-16: Edge color resolved from edge-types.json colorToken
- [x] ISC-17: `dashed` edge style rendered as dashed stroke
- [x] ISC-18: `dashed-double` edge style rendered distinctly
- [x] ISC-19: Unknown edgeClass falls back to `structural` (no crash)
- [x] ISC-20: Dangling edges (endpoint not in node set) filtered out (no throw)
- [x] ISC-21: Clicking a node calls `onNodeSelect(node.id)`
- [x] ISC-22: `selectedNodeId` node shows a selection ring/highlight
- [x] ISC-23: Cost overlay shows `$cost` when `overlays.has('cost')` and cost present
- [x] ISC-24: No cost label when cost is missing even with overlay on
- [x] ISC-25: `fitView` frames the graph (fixes low/cut-off complaint)
- [x] ISC-26: Empty nodes/edges render without crash
- [x] ISC-27: Props default (nodes=[], edges=[], overlays=new Set()) preserved
- [x] ISC-28: All 12 cases in ExplodedCanvas.test.jsx preserved (none deleted/skipped)
- [x] ISC-29: Unit test file passes against the React Flow implementation
- [x] ISC-30: recruiter-ui production build succeeds with the change
- [x] ISC-31: Dev DB seed runs idempotently under org cosmicinc (no error)
- [x] ISC-32: Seed wrote contracts rows for org cosmicinc (verified via SELECT)
- [x] ISC-33: Seed wrote contract_edges rows for org cosmicinc (verified via SELECT)
- [x] ISC-34: Manual quality pass run on renderer diff (layout-memo efficiency fix applied; /simplify skipped — changes live in a separate repo the in-context skill can't target)

### Anti-criteria
- [x] ISC-A1: PROD (Railway `production`) DB is NOT touched
- [x] ISC-A2: No existing test deleted, `.skip`'d, or weakened
- [x] ISC-A3: No temp Clerk-bypass committed to layout.jsx

## Decisions

- Renderer = React Flow (@xyflow/react), per user choice over ApexCharts (which cannot draw
  node-link graphs). d3-force reused for static layout only (it's already a dep).
- Seed target org = cosmicinc (maceo@cosmicinc.ai), not legacy_default (which is the local
  AUTH_ENABLED=false dev-admin org, not what deployed dev users authenticate as).

## Verification

- **Unit tests (ISC-3..29, 34):** `vitest run` (worktree-local single-React config) →
  `recruiter-ui/__tests__/components/contract/ExplodedCanvas.test.jsx (11 tests) ... Tests 11 passed (11)`.
  Re-run green after the layout-memo refactor. All 11 original cases preserved (none deleted/skipped).
  NOTE: PRD said "12 cases" — the file actually has 11; corrected.
- **Production build (ISC-30):** `npm run build` (recruiter-ui) → `✓ Compiled successfully in 5.3s`,
  `✓ Generating static pages (25/25)`. Zero errors referencing exploded/xyflow/d3-force. (Needed the
  prebuilt `@cosmic/ds` dist copied into node_modules — a pre-existing worktree env gap, not the change.)
- **Dep (ISC-1):** package.json shows `"@xyflow/react": "^12.3.5"`; installed `@xyflow/react@12.11.1`.
- **Seed (ISC-31..33, A1):** ran `seed-contract-explode-demo.cjs` against dev public URL
  `trolley.proxy.rlwy.net:24846` under `SEED_ORG_ID=6a6a0732…`. Output: contracts 12, contract_edges 25,
  vendor_records 7, interview_extractions 1. SELECT verify under org 6a6a0732: contracts=12, edges=25,
  vendors=7, extraction=1. Only the `development` env URL was ever used (prod untouched).
- **Clean diff (A2/A3):** committable files = ExplodedCanvas.jsx, ExplodedCanvas.test.jsx,
  package.json, package-lock.json. No layout.jsx bypass; no test deletions.

### Memory cards

#### Q-renderer
mode: root
source: algorithm-cv-graph-reactflow-learn
body: ApexCharts (any version) has NO node-link/force-directed/network/sankey chart type — 23
chart types, all statistical. For a dependency/relationship/blast-radius graph in a React/Metronic
app, use React Flow (@xyflow/react); reuse the already-present d3-force ONLY for a static one-shot
layout (tick().stop()) and let React Flow own rendering + fitView (fixes cut-off framing).

#### Q-worktree-react
mode: root
source: algorithm-cv-graph-reactflow-learn
body: cosmic-HR vitest.config.js resolves react/react-dom from the MAIN clone (findMainRepoDir
follows the worktree .git pointer). A new react-rendering dep installed only in a worktree →
dual-React "Cannot read properties of null (reading useRef)". Fix for local verify: a throwaway
vitest config rooted at the worktree (alias react/react-dom/@testing-library to the worktree
node_modules + dedupe + inline the dep). For a normal single clone there's one react on disk so it's
a non-issue. Also: @cosmic/ds (file: design-system) must have a built dist/ or every consumer 404s.

