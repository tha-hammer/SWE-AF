"""Shared subprocess/output helpers for the deterministic check layer.

Promoted out of ``ci_gate`` so both the post-PR CI gate and the inner-loop
deterministic runner (``deterministic_check``) share one ``_tail`` implementation
instead of duplicating it. ``ci_gate`` re-exports these names for backwards
compatibility (``tests/test_ci_gate.py`` imports ``_tail`` from ``ci_gate``).
"""

from __future__ import annotations

# Per-failure log tail size. Big enough to surface the actual error, small
# enough to keep the fixer prompt under control across multi-failure runs.
_LOG_TAIL_CHARS: int = 3000


def _tail(text: str, max_chars: int = _LOG_TAIL_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return "…[truncated]…\n" + text[-max_chars:]
