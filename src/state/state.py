"""The observable state carried between LangGraph nodes."""

from typing import Any, Dict, List, TypedDict

from typing_extensions import Literal

from src.schemas.models import SourcePolicy


StatusType = Literal[
    "created", "planning_research", "research_plan_ready", "searching_sources",
    "sources_discovered", "previewing_sources", "sources_previewed", "evaluating_sources", "sources_evaluated", "sources_selected", "exploring_sites", "site_exploration_complete", "selecting_sources", "designing_schema",
    "waiting_for_schema_approval", "schema_approved", "scraping_sources",
    "processing", "chunking", "routing_extraction", "extracting_data", "binding_evidence", "validating_evidence", "quality_gating", "resolving_records", "merging", "classifying", "enriching", "extracting_entities",
    "extracting_relations", "quality_check", "normalizing", "validating", "deduplicating",
    "exporting", "writing_dataset", "completed", "failed", "cancelled", "acquiring",
]


class AgentState(TypedDict):
    domain: str
    config: Dict[str, Any]
    dataset_name: str
    dataset_topic: str
    dataset_purpose: str
    source_policy: Dict[str, Any]
    research_plan: Dict[str, Any]
    source_registry: Dict[str, Dict[str, Any]]
    candidate_sources: List[Dict[str, Any]]
    source_previews: List[Dict[str, Any]]
    source_evaluations: List[Dict[str, Any]]
    source_selections: List[Dict[str, Any]]
    source_selection_metrics: Dict[str, Any]
    selected_sources: List[Dict[str, Any]]
    rejected_sources: List[Dict[str, Any]]
    explored_site_starts: List[str]
    site_exploration_results: List[Dict[str, Any]]
    schema_design_input: Dict[str, Any]
    draft_dataset_schema: Dict[str, Any]
    approved_dataset_schema: Dict[str, Any]
    acquired_documents: List[Dict[str, Any]]
    acquisition_metrics: Dict[str, Any]
    scraped_documents: List[Dict[str, Any]]
    processed_documents: List[Dict[str, Any]]
    content_processing_metrics: Dict[str, Any]
    clean_documents: List[Dict[str, Any]]
    document_chunks: List[Dict[str, Any]]
    extraction_routes: List[Dict[str, Any]]
    deterministic_extraction_results: List[Dict[str, Any]]
    deterministic_extraction_batches: List[Dict[str, Any]]
    extraction_routing_metrics: Dict[str, Any]
    extraction_batches: List[Dict[str, Any]]
    evidenced_extraction_batches: List[Dict[str, Any]]
    evidence_metrics: Dict[str, Any]
    evidence_warnings: List[str]
    evidence_rejections: List[Dict[str, Any]]
    verified_records: List[Dict[str, Any]]
    evidence_validation_metrics: Dict[str, Any]
    quality_approved_extraction_batches: List[Dict[str, Any]]
    record_quality_assessments: List[Dict[str, Any]]
    quality_gate_metrics: Dict[str, Any]
    quality_gate_rejections: List[Dict[str, Any]]
    resolved_records: List[Dict[str, Any]]
    record_resolution_metrics: Dict[str, Any]
    extraction_warnings: List[str]
    chunk_extraction_results: List[Dict[str, Any]]
    merged_records: List[Dict[str, Any]]
    extraction_results: List[Dict[str, Any]]
    accepted_records: List[Dict[str, Any]]
    rejected_records: List[Dict[str, Any]]
    raw_data: List[Dict[str, Any]]
    processed_data: List[Dict[str, Any]]
    classified_data: List[Dict[str, Any]]
    enriched_data: List[Dict[str, Any]]
    validated_data: List[Dict[str, Any]]
    validation_report: Dict[str, Any]
    deduplication_metrics: Dict[str, Any]
    output_profiles: List[str]
    output_paths: Dict[str, str]
    errors: List[Dict[str, Any]]
    status: StatusType
    pipeline_status: StatusType


def create_initial_state(domain: str, config: Dict[str, Any]) -> AgentState:
    dataset_config = config.get("dataset", {})
    source_config = config.get("sources", {})
    raw_policy = source_config.get("source_policy", {}) if isinstance(source_config, dict) else {}
    source_policy = SourcePolicy.model_validate(raw_policy).model_dump(mode="json")
    return {
        "domain": domain,
        "config": config,
        "dataset_name": dataset_config.get("name", ""),
        "dataset_topic": dataset_config.get("topic", ""),
        "dataset_purpose": dataset_config.get("purpose", ""),
        "source_policy": source_policy,
        "research_plan": {},
        "source_registry": {},
        "candidate_sources": [],
        "source_previews": [],
        "source_evaluations": [],
        "source_selections": [],
        "source_selection_metrics": {},
        "selected_sources": [],
        "rejected_sources": [],
        "explored_site_starts": [],
        "site_exploration_results": [],
        "schema_design_input": {},
        "draft_dataset_schema": {},
        "approved_dataset_schema": {},
        "acquired_documents": [],
        "acquisition_metrics": {},
        "scraped_documents": [],
        "processed_documents": [],
        "content_processing_metrics": {},
        "clean_documents": [],
        "document_chunks": [],
        "extraction_routes": [],
        "deterministic_extraction_results": [],
        "deterministic_extraction_batches": [],
        "extraction_routing_metrics": {},
        "extraction_batches": [],
        "evidenced_extraction_batches": [],
        "evidence_metrics": {},
        "evidence_warnings": [],
        "evidence_rejections": [],
        "verified_records": [],
        "evidence_validation_metrics": {},
        "quality_approved_extraction_batches": [],
        "record_quality_assessments": [],
        "quality_gate_metrics": {},
        "quality_gate_rejections": [],
        "resolved_records": [],
        "record_resolution_metrics": {},
        "extraction_warnings": [],
        "chunk_extraction_results": [],
        "merged_records": [],
        "extraction_results": [],
        "accepted_records": [],
        "rejected_records": [],
        "raw_data": [],
        "processed_data": [],
        "classified_data": [],
        "enriched_data": [],
        "validated_data": [],
        "validation_report": {},
        "deduplication_metrics": {},
        "output_profiles": [],
        "output_paths": {},
        "errors": [],
        "status": "created" if dataset_config.get("topic") else "acquiring",
        "pipeline_status": "created" if dataset_config.get("topic") else "acquiring",
    }
