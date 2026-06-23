"""Build-budget finalize: a green build must not be reported 'failed' by the
agentfield runtime watchdog. build() owns a wall-clock budget and finalizes the
completed work before the watchdog can cancel it."""

from __future__ import annotations

import os
import time

_ENV_KEYS = ("NODE_ID", "SWE_DEFAULT_MODEL", "AI_MODEL", "HARNESS_MODEL", "default_execution_timeout")
_PRE_IMPORT_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}

os.environ.setdefault("AGENTFIELD_SERVER", "http://localhost:9999")

import swe_af.app as app_mod  # noqa: E402
from swe_af.execution.schemas import BuildConfig  # noqa: E402

for _key, _value in _PRE_IMPORT_ENV.items():
    if _value is None:
        os.environ.pop(_key, None)
    else:
        os.environ[_key] = _value


# --- budget computation -------------------------------------------------------


def test_effective_budget_explicit_override_wins():
    cfg = BuildConfig(build_budget_seconds=1234)
    assert app_mod._effective_build_budget_seconds(cfg) == 1234.0


def test_effective_budget_auto_derives_from_watchdog_env(monkeypatch):
    monkeypatch.setenv("default_execution_timeout", "21600")
    cfg = BuildConfig(build_budget_buffer_seconds=1800)
    # 21600 - 1800 = 19800
    assert app_mod._effective_build_budget_seconds(cfg) == 19800.0


def test_effective_budget_default_watchdog_when_env_absent(monkeypatch):
    monkeypatch.delenv("default_execution_timeout", raising=False)
    monkeypatch.delenv("DEFAULT_EXECUTION_TIMEOUT", raising=False)
    cfg = BuildConfig(build_budget_buffer_seconds=600)
    # default watchdog 7200 - 600 = 6600
    assert app_mod._effective_build_budget_seconds(cfg) == 6600.0


def test_effective_budget_never_negative(monkeypatch):
    monkeypatch.setenv("default_execution_timeout", "100")
    cfg = BuildConfig(build_budget_buffer_seconds=99999)
    assert app_mod._effective_build_budget_seconds(cfg) >= 60.0


# --- budget exhaustion --------------------------------------------------------


def test_budget_exhausted_when_elapsed_exceeds():
    assert app_mod._build_budget_exhausted(time.monotonic() - 1000, 500) is True


def test_budget_not_exhausted_when_within():
    assert app_mod._build_budget_exhausted(time.monotonic(), 500) is False


def test_budget_disabled_never_exhausted():
    assert app_mod._build_budget_exhausted(time.monotonic() - 10_000, 0) is False


# --- finalize semantics: deferred verification → completed_with_debt, NOT failed


def test_deferred_verification_finalizes_completed_with_debt_not_failed():
    # This is what the budget gate produces: verification is skipped (None) and a
    # verification_incomplete debt item is recorded. The terminal status must be
    # completed_with_debt — a green-with-caveat result — never "failed".
    dag_result = {
        "completed_issues": [{"issue_name": "a"}],
        "failed_issues": [],
        "accumulated_debt": [{
            "type": "verification_incomplete",
            "criterion": "full acceptance verification",
            "reason": "build time budget reached before verification completed",
            "severity": "medium",
        }],
    }
    status = app_mod._execution_status(None, dag_result)
    assert status == "completed_with_debt"
    assert status != "failed"
