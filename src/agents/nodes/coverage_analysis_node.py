"""Coverage ledger node executed after persistent knowledge writing."""

from typing import Any

from src.knowledge.coverage import analyze_coverage


def coverage_analysis_node(state: dict[str, Any]) -> dict[str, Any]:
    try:
        return analyze_coverage(state)
    except Exception as exc:
        return {"coverage_metrics": {"enabled": bool(state.get("config", {}).get("storage", {}).get("enabled")), "error": str(exc)}, "coverage_states": [], "research_tasks": []}
