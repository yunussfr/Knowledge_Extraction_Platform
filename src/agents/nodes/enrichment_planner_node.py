"""Turn pending coverage tasks into bounded, auditable research queries."""

from typing import Any


def enrichment_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    tasks = [task for task in state.get("research_tasks", []) if task.get("status") == "pending"]
    loop = state.get("config", {}).get("research_loop", {})
    max_tasks = int(loop.get("max_tasks_per_round", 25)) if isinstance(loop, dict) else 25
    selected = tasks[:max_tasks]
    plan = dict(state.get("research_plan") or {})
    queries = [
        task.get("query_context", {}).get("query", f"{task.get('field_name', '')}")
        if isinstance(task.get("query_context"), dict) else str(task.get("field_name", ""))
        for task in selected
    ]
    if queries:
        plan["search_queries"] = queries
    return {
        "enrichment_queries": queries,
        "research_plan": plan,
        "enrichment_round": int(state.get("enrichment_round", 0)) + (1 if selected else 0),
        "enrichment_metrics": {"pending_tasks": len(tasks), "planned_tasks": len(selected), "budget": max_tasks},
    }
