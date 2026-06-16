from __future__ import annotations

import os

_ENV_KEYS = ("NODE_ID", "SWE_DEFAULT_MODEL", "AI_MODEL", "HARNESS_MODEL")
_PRE_IMPORT_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}

os.environ.setdefault("AGENTFIELD_SERVER", "http://localhost:9999")

import swe_af.app as app_mod  # noqa: E402
from swe_af.execution.schemas import BuildResult, RepoPRResult  # noqa: E402

for _key, _value in _PRE_IMPORT_ENV.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


def test_high_severity_debt_returns_completed_with_debt_status() -> None:
    status = app_mod._final_build_status(
        verification={"passed": True, "summary": "ok"},
        dag_result={"accumulated_debt": [{"severity": "high"}], "failed_issues": []},
        pr_results=[],
        pr_expected=False,
    )

    assert status == "completed_with_debt"


def test_missing_expected_pr_returns_failed_status() -> None:
    status = app_mod._final_build_status(
        verification={"passed": True, "summary": "ok"},
        dag_result={"accumulated_debt": [], "failed_issues": []},
        pr_results=[],
        pr_expected=True,
    )

    assert status == "failed"


def test_successful_pr_and_clean_verification_returns_completed_status() -> None:
    status = app_mod._final_build_status(
        verification={"passed": True, "summary": "ok"},
        dag_result={"accumulated_debt": [], "failed_issues": []},
        pr_results=[
            RepoPRResult(
                repo_name="repo",
                repo_url="https://github.com/o/r.git",
                success=True,
                pr_url="https://github.com/o/r/pull/1",
            )
        ],
        pr_expected=True,
    )

    assert status == "completed"


def test_build_result_defaults_status_from_success_for_compat() -> None:
    result = BuildResult(plan_result={}, dag_state={}, success=False, summary="failed")

    assert result.status == "failed"
    assert result.model_dump()["status"] == "failed"
