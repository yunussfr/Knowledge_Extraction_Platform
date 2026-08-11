"""The observable state carried between LangGraph nodes."""

from typing import Any, Dict, List, TypedDict

from typing_extensions import Literal


StatusType = Literal[
    "created", "planning_research", "research_plan_ready", "searching_sources",
    "sources_discovered", "evaluating_sources", "sources_selected", "designing_schema",
    "waiting_for_schema_approval", "schema_approved", "scraping_sources",
    "processing", "extracting_data", "classifying", "enriching", "extracting_entities",
    "extracting_relations", "quality_check", "normalizing", "validating", "deduplicating",
    "exporting", "writing_dataset", "completed", "failed", "cancelled", "acquiring",
]


class AgentState(TypedDict):
    domain: str
    config: Dict[str, Any]
    dataset_name: str
    dataset_topic: str
    dataset_purpose: str
    research_plan: Dict[str, Any]
    candidate_sources: List[Dict[str, Any]]
    selected_sources: List[Dict[str, Any]]
    rejected_sources: List[Dict[str, Any]]
    draft_dataset_schema: Dict[str, Any]
    approved_dataset_schema: Dict[str, Any]
    scraped_documents: List[Dict[str, Any]]
    extraction_results: List[Dict[str, Any]]
    accepted_records: List[Dict[str, Any]]
    rejected_records: List[Dict[str, Any]]
    raw_data: List[Dict[str, Any]]
    processed_data: List[Dict[str, Any]]
    classified_data: List[Dict[str, Any]]
    enriched_data: List[Dict[str, Any]]
    validated_data: List[Dict[str, Any]]
    validation_report: Dict[str, Any]
    errors: List[Dict[str, Any]]
    status: StatusType
    pipeline_status: StatusType


def create_initial_state(domain: str, config: Dict[str, Any]) -> AgentState:
    dataset_config = config.get("dataset", {})
    return {
        "domain": domain,
        "config": config,
        "dataset_name": dataset_config.get("name", ""),
        "dataset_topic": dataset_config.get("topic", ""),
        "dataset_purpose": dataset_config.get("purpose", ""),
        "research_plan": {},
        "candidate_sources": [],
        "selected_sources": [],
        "rejected_sources": [],
        "draft_dataset_schema": {},
        "approved_dataset_schema": {},
        "scraped_documents": [],
        "extraction_results": [],
        "accepted_records": [],
        "rejected_records": [],
        "raw_data": [],
        "processed_data": [],
        "classified_data": [],
        "enriched_data": [],
        "validated_data": [],
        "validation_report": {},
        "errors": [],
        "status": "created" if dataset_config.get("topic") else "acquiring",
        "pipeline_status": "created" if dataset_config.get("topic") else "acquiring",
    }
