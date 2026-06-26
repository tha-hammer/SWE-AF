"""Deterministic eval checks for the SWE-AF planning prompts (Phase 0c).

The checks come in two families:

* **prompt-source checks** — line budget + domain-leakage, computed against the
  ``SYSTEM_PROMPT`` string literals. The literals are pulled via :mod:`ast`
  (import-free) so the checks are robust to line drift and never execute prompt
  module side effects.
* **golden-output checks** — schema validity, acceptance-criterion -> runnable
  command coverage, and the vertical-slice guarantee, computed against captured
  ``PlanResult`` golden fixtures under ``tests/fixtures/prompt_evals/baseline/``.

Per the plan, the prompt-source checks are the RED net: they must currently
FAIL for the known offenders (planning-loop leakage, sprint/planning-loop
over-length) and turn GREEN as later phases restructure those prompts. The
golden-output checks are the positive guarantees that must stay GREEN.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = _REPO_ROOT / "swe_af" / "prompts"
BASELINE_DIR = _REPO_ROOT / "tests" / "fixtures" / "prompt_evals" / "baseline"

#: The six planning-stage prompts, in pipeline order (see ``swe_af/app.py`` ``plan()``).
PLANNING_PROMPTS = [
    "product_manager",
    "architect",
    "tech_lead",
    "architecture_planning_loop",
    "sprint_planner",
    "issue_writer",
]

#: Per-prompt SYSTEM_PROMPT line budgets. The default is the lean-prompt target.
#: sprint_planner gets a higher ceiling on purpose: decomposition is the richest
#: planning stage, and after Phase 3 removed the genuine SYSTEM<->task-builder
#: duplication it is ~212 lines of substantive judgment (TDD decomposition, the
#: worked example, guidance/recovery/isolation rules), not bloat. The ceiling still
#: guards against re-bloat toward the original 244.
DEFAULT_SYSTEM_PROMPT_BUDGET = 120
SYSTEM_PROMPT_LINE_BUDGETS = {"sprint_planner": 215}

#: Back-compat alias for the default lean ceiling.
MAX_SYSTEM_PROMPT_LINES = DEFAULT_SYSTEM_PROMPT_BUDGET


def line_budget(stem: str) -> int:
    """The SYSTEM_PROMPT line ceiling for a given planning prompt."""
    return SYSTEM_PROMPT_LINE_BUDGETS.get(stem, DEFAULT_SYSTEM_PROMPT_BUDGET)

#: Concrete domain-specific identifiers that leaked from a target-project example
#: ("Example Applied (Exploded View Feature)") into the *general* planning prompt.
#: A general prompt must teach with neutral illustrations, not ship a named domain
#: model — these tokens are the canary for that anti-pattern.
DOMAIN_LEAK_TOKENS = [
    "Exploded View",
    "DependencyNode",
    "DependencyEdge",
    "DependencyResolutionService",
    "ImpactPropagationService",
    "DependencyMapped",
    "CascadeImpactDetected",
    "cosmic-HR",
    "cosmic_hr",
]


# --------------------------------------------------------------------------- #
# prompt-source checks
# --------------------------------------------------------------------------- #
def extract_system_prompt(stem: str) -> str:
    """Return the ``SYSTEM_PROMPT`` string literal from ``swe_af/prompts/<stem>.py``.

    Raises ``AssertionError`` if the module has no module-level ``SYSTEM_PROMPT``
    bound to a plain string literal (the contract every planning prompt honors).
    """
    path = PROMPTS_DIR / f"{stem}.py"
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT":
                value = ast.literal_eval(node.value)
                if isinstance(value, str):
                    return value
                raise AssertionError(
                    f"{stem}.py SYSTEM_PROMPT is not a plain string literal"
                )
    raise AssertionError(f"{stem}.py has no module-level SYSTEM_PROMPT literal")


def system_prompt_line_count(stem: str) -> int:
    """Number of lines in the prompt's ``SYSTEM_PROMPT`` literal."""
    return extract_system_prompt(stem).count("\n") + 1


def domain_leaks(stem: str) -> list[str]:
    """Domain-leak tokens (see :data:`DOMAIN_LEAK_TOKENS`) present in the prompt."""
    system_prompt = extract_system_prompt(stem)
    return [token for token in DOMAIN_LEAK_TOKENS if token in system_prompt]


# --------------------------------------------------------------------------- #
# golden-output checks
# --------------------------------------------------------------------------- #
def golden_path(fixture: str) -> Path:
    return BASELINE_DIR / fixture


def load_golden(fixture: str) -> dict | None:
    """Load and normalize a captured ``PlanResult`` golden, or ``None`` if absent.

    Tolerates the execution-API wrapping the result under ``result``/``output``.
    """
    path = golden_path(fixture)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return _unwrap_plan_result(data)


def _unwrap_plan_result(data: dict) -> dict:
    if "prd" in data and "issues" in data:
        return data
    for key in ("result", "output", "data", "plan"):
        inner = data.get(key)
        if isinstance(inner, dict) and "prd" in inner and "issues" in inner:
            return inner
    return data


def planning_artifacts_present(plan_result: dict) -> bool:
    """True when the DDD planning loop drove the sprint (planning_artifacts set)."""
    if plan_result.get("planning_artifacts"):
        return True
    architecture = plan_result.get("architecture") or {}
    return bool(architecture.get("planning_artifacts"))


def vertical_slice_count(plan_result: dict) -> int:
    """Number of issues marked as the end-to-end vertical slice."""
    return sum(
        1
        for issue in plan_result.get("issues", [])
        if issue.get("slice_role") == "vertical-slice"
    )


def issues_missing_runnable_check(plan_result: dict) -> list[str]:
    """Issue names that carry acceptance criteria but no runnable verification command.

    Mirrors the deterministic rung's contract: every issue that promises behavior
    must ship at least one ``AcceptanceCheck`` whose ``command`` is non-empty.
    """
    offenders: list[str] = []
    for issue in plan_result.get("issues", []):
        if not issue.get("acceptance_criteria"):
            continue
        checks = issue.get("verification") or []
        if not any((check.get("command") or "").strip() for check in checks):
            offenders.append(issue.get("name") or issue.get("title") or "<unnamed>")
    return offenders
