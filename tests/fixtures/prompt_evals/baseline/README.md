# Golden planning baselines (SWE-AF-ixn Phase 0b)

Captured 2026-06-26 via the live `swe-planner.plan` reasoner (control-plane :8080).
Node=`swe-planner`, provider=`claude`, all six role models pinned to `sonnet`.
Repo: `/workspaces/dev/_prompt-eval-scratch` (buildstats scratch service).

These are observed-behavior reference snapshots for the eval net in `tests/prompt_evals/`.
They are NOT exact-match assertions — later phases diff against them for semantic regression.

| goal | fixture | exec id | dur | issues | planning_artifacts | vertical-slice |
|---|---|---|---|---|---|---|
| A | `goal_a_version_flag.json` | `exec_20260626_161451_bd7iznuy` | 1165s | 1 | True | 1 |
| B | `goal_b_build_metrics.json` | `exec_20260626_161456_zzif2rv8` | 1828s | 6 | True | 1 |

Goal A: Add a --version flag to the buildstats CLI that prints the package version and exits 0.

Goal B: Add a build-metrics bounded context to buildstats: persist each build run's id, start time, end time, exit status, and expose avg duration + success rate over last N runs.
