import json
from typing import Any, Dict

from src.agents.prompts import RESEARCH_PLANNER_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import ResearchPlan, ResearchPlannerInput, ResearchQueryFamily
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def build_research_planner_input(state: Dict[str, Any]) -> ResearchPlannerInput:
    """Build the typed planner boundary without inventing absent restrictions."""
    config = state.get("config", {})
    research = config.get("research", {})
    source_config = config.get("sources", {})
    if not isinstance(source_config, dict):
        source_config = {}
    source_policy = state.get("source_policy")
    if source_policy is None:
        source_policy = source_config.get("source_policy", {})
    requested_query_count = research.get("queries", 10)
    return ResearchPlannerInput(
        dataset_topic=state.get("dataset_topic", ""),
        dataset_purpose=state.get("dataset_purpose", ""),
        source_policy=source_policy,
        seed_urls=source_config.get("seed_urls", []),
        preferred_domains=source_config.get("preferred_domains", []),
        allowed_domains=source_config.get("allowed_domains"),
        blocked_domains=source_config.get("blocked_domains"),
        query_count=requested_query_count,
        constraints=research.get("constraints", ""),
    )


def research_planner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        planner_input = build_research_planner_input(state)
        topic = planner_input.dataset_topic
        logger.info("Planning research for dataset topic: %s", topic)
        research = state.get("config", {}).get("research", {})
        if not topic:
            return {"research_plan": {}, "status": "research_plan_ready", "pipeline_status": "research_plan_ready"}
        if settings.data_source_provider == "mock":
            queries = [topic]
            plan = ResearchPlan(
                research_topic=topic,
                subtopics=[topic],
                search_queries=queries,
                preferred_source_types=planner_input.source_policy.preferred_source_types,
                excluded_source_types=planner_input.source_policy.blocked_source_types or [],
                query_families=[ResearchQueryFamily(
                    name="general",
                    purpose="Configured or topic-derived baseline queries.",
                    queries=queries,
                )],
            )
        else:
            user_prompt = json.dumps(
                {
                    "planner_input": planner_input.model_dump(mode="json"),
                    "query_requirements": {
                        "exact_count": planner_input.query_count,
                        "instruction": (
                            "Return exactly exact_count unique, non-empty search queries. "
                            "Do not return fewer queries and do not return an empty list."
                        ),
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            plan = GroqClient().complete_json(RESEARCH_PLANNER_SYSTEM_PROMPT, user_prompt, ResearchPlan)
            if not plan.research_topic.strip():
                plan.research_topic = topic
            if len(plan.search_queries) != planner_input.query_count:
                raise ValueError(
                    "Research planner returned "
                    f"{len(plan.search_queries)} queries; exactly "
                    f"{planner_input.query_count} are required."
                )
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
