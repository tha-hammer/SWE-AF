from __future__ import annotations

import pytest

from swe_af.execution.dag_executor import run_dag
from swe_af.execution.fatal_error import AuthHarnessError
from swe_af.execution.schemas import ExecutionConfig


@pytest.mark.asyncio
async def test_fatal_auth_error_aborts_dag_and_skips_unfinished_issues(tmp_path) -> None:
    calls: list[str] = []

    async def execute_fn(issue: dict, dag_state) -> None:
        calls.append(issue["name"])
        raise AuthHarnessError(
            'API Error: 401 {"type":"authentication_error"} Please run /login'
        )

    plan_result = {
        "issues": [
            {"name": "auth-root", "acceptance_criteria": []},
            {"name": "downstream", "depends_on": ["auth-root"], "acceptance_criteria": []},
        ],
        "levels": [["auth-root"], ["downstream"]],
        "artifacts_dir": str(tmp_path / ".artifacts"),
    }

    state = await run_dag(
        plan_result=plan_result,
        repo_path=str(tmp_path),
        execute_fn=execute_fn,
        config=ExecutionConfig(max_retries_per_issue=0),
    )

    assert calls == ["auth-root"]
    assert [f.issue_name for f in state.failed_issues] == ["auth-root"]
    assert state.skipped_issues == ["downstream"]
    assert state.current_level == len(state.levels)
