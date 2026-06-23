"""Behavior 9: documentation captures the current and future architecture."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_DOC = _ROOT / "docs" / "ARCHITECTURE.md"
README_DOC = _ROOT / "README.md"


def test_architecture_docs_describe_ddd_planning_loop():
    content = ARCHITECTURE_DOC.read_text()
    assert "DDD Planning Loop" in content
    assert "Modular Monolith" in content
    assert "Internal Event Backbone" in content
    assert "CQRS-lite" in content


def test_architecture_docs_describe_extraction_and_observability():
    content = ARCHITECTURE_DOC.read_text()
    assert "vertical slice" in content.lower()
    assert "extraction strategy" in content.lower()
    assert "observability" in content.lower()


def test_readme_mentions_ddd_planning_loop():
    content = README_DOC.read_text()
    assert "DDD Planning Loop" in content
