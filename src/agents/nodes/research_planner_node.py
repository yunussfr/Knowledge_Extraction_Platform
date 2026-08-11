from typing import Any, Dict

from src.agents.prompts import RESEARCH_PLANNER_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import ResearchPlan
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def research_planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        topic = state.get("dataset_topic", "")
        logger.info("Planning research for dataset topic: %s", topic)
        research = state.get("config", {}).get("research", {})
        if not topic:
            return {"research_plan": {}, "status": "research_plan_ready", "pipeline_status": "research_plan_ready"}
        if settings.data_source_provider == "mock":
            plan = ResearchPlan(
                research_topic=topic,
                subtopics=[topic],
                search_queries=(research.get("queries") or [topic])[:research.get("max_queries", settings.default_max_search_queries)],
                preferred_source_types=["institutional", "academic"],
            )
        else:
            user_prompt = (
                f"Dataset topic: {topic}\nPurpose: {state.get('dataset_purpose', '')}\n"
                f"Maximum search queries: {research.get('max_queries', settings.default_max_search_queries)}\n"
                f"Preferred domains: {research.get('preferred_domains', [])}\n"
                f"User research constraints: {research.get('constraints', '')}"
            )
            plan = GroqClient().complete_json(RESEARCH_PLANNER_SYSTEM_PROMPT, user_prompt, ResearchPlan)
        logger.info("Research plan ready with %d search queries.", len(plan.search_queries))
        return {
            "research_plan": plan.model_dump(),
            "status": "research_plan_ready",
            "pipeline_status": "research_plan_ready",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "research_planner", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
