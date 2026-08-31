"""Single LangGraph pipeline for Knowledge_extraction_agent."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from src.core.logging import get_logger
from src.agents.nodes.acquisition_node import acquisition_node
from src.agents.nodes.classification_node import classification_node
from src.agents.nodes.chunking_node import chunking_node
from src.agents.nodes.checkpoint_node import checkpoint_node
from src.agents.nodes.dataset_schema_designer_node import dataset_schema_designer_node
from src.agents.nodes.deduplication_node import deduplication_node
from src.agents.nodes.entity_extraction_node import entity_extraction_node
from src.agents.nodes.evidence_validation_node import evidence_validation_node
from src.agents.nodes.extraction_router_node import extraction_router_node
from src.agents.nodes.field_evidence_node import field_evidence_node
from src.agents.nodes.export_node import export_node
from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.manifest_node import manifest_node
from src.agents.nodes.normalization_node import normalization_node
from src.agents.nodes.processing_node import processing_node
from src.agents.nodes.quality_gate_node import quality_gate_node
from src.agents.nodes.quality_analysis_node import quality_analysis_node
from src.agents.nodes.relation_extraction_node import relation_extraction_node
from src.agents.nodes.record_resolution_node import record_resolution_node
from src.agents.nodes.research_planner_node import research_planner_node
from src.agents.nodes.source_evaluator_node import source_evaluator_node
from src.agents.nodes.source_preview_node import source_preview_node
from src.agents.nodes.site_exploration_node import site_exploration_node
from src.agents.nodes.source_selector_node import source_selector_node
from src.agents.nodes.source_search_node import source_search_node
from src.agents.nodes.structured_extraction_node import structured_extraction_node
from src.agents.nodes.storage_node import storage_node
from src.agents.nodes.validation_node import validation_node
from src.schemas.models import ApprovedDatasetSchema, DraftDatasetSchema
from src.state.state import AgentState


logger = get_logger(__name__)


def _entry_node(_: AgentState) -> Dict[str, Any]:
    return {}

#This function examines the current state and decides which node the pipeline will proceed to
def _entry_route(state: AgentState) -> str:
    if state.get("resume_from"):
        return state["resume_from"]
    if state.get("status") in {"failed", "cancelled", "waiting_for_schema_approval"}:
        return END
    if state.get("approved_dataset_schema") and state.get("status") == "schema_approved":
        return "acquisition"
    return "research_planner" if state.get("dataset_topic") else "acquisition"


def _schema_route(state: AgentState) -> str:
    return END if state.get("status") in {"failed", "waiting_for_schema_approval", "cancelled"} else "acquisition"


def _processing_route(state: AgentState) -> str:
    if state.get("status") == "failed":
        return END
    return "chunking" if state.get("approved_dataset_schema") else "classification"


def _checkpoint_processing_route(state: AgentState) -> str:
    return "chunking" if state.get("approved_dataset_schema") else "classification"


def _next_or_end(next_node: str):
    """Prevent a later node from masking an earlier node failure."""
    def route(state: AgentState) -> str:
        return END if state.get("status") in {"failed", "cancelled"} else next_node
    return route


def _validate_draft_schema(draft: DraftDatasetSchema) -> None:
    names = [field.field_name for field in draft.fields]
    if len(names) != len(set(names)):
        raise ValueError("Schema field names must be unique.")
    for field in draft.fields:
        is_array_type = field.type == "array" or field.type.startswith("array[")
        if field.is_array != is_array_type:
            raise ValueError(f"Field {field.field_name} has inconsistent array type metadata.")


class DatasetGenerationPipeline:
    """Owns schema approval and resumes the same compiled LangGraph after approval."""

    def __init__(self) -> None:
        workflow = StateGraph(AgentState)
        workflow.add_node("entry", _entry_node)
        workflow.add_node("research_planner", research_planner_node)
        workflow.add_node("source_search", source_search_node)
        workflow.add_node("source_preview", source_preview_node)
        workflow.add_node("source_evaluator", source_evaluator_node)
        workflow.add_node("site_exploration", site_exploration_node)
        workflow.add_node("source_selector", source_selector_node)
        workflow.add_node("dataset_schema_designer", dataset_schema_designer_node)
        workflow.add_node("acquisition", acquisition_node)
        workflow.add_node("processing", processing_node)
        workflow.add_node("chunking", chunking_node)
        workflow.add_node("extraction_router", extraction_router_node)
        workflow.add_node("structured_extraction", structured_extraction_node)
        workflow.add_node("field_evidence", field_evidence_node)
        workflow.add_node("evidence_validation", evidence_validation_node)
        workflow.add_node("quality_gate", quality_gate_node)
        workflow.add_node("record_resolution", record_resolution_node)
        workflow.add_node("deduplication", deduplication_node)
        workflow.add_node("classification", classification_node)
        workflow.add_node("metadata_enrichment", metadata_enrichment_node)
        workflow.add_node("entity_extraction", entity_extraction_node)
        workflow.add_node("relation_extraction", relation_extraction_node)
        workflow.add_node("quality_analysis", quality_analysis_node)
        workflow.add_node("normalization", normalization_node)
        workflow.add_node("validation", validation_node)
        workflow.add_node("export", export_node)
        workflow.add_node("manifest", manifest_node)
        workflow.add_node("storage", storage_node)
        workflow.add_node("checkpoint_sources", checkpoint_node("sources"))
        workflow.add_node("checkpoint_acquisition", checkpoint_node("acquisition"))
        workflow.add_node("checkpoint_processing", checkpoint_node("processing"))
        workflow.add_node("checkpoint_chunking", checkpoint_node("chunking"))
        workflow.add_node("checkpoint_extraction", checkpoint_node("extraction"))
        workflow.add_node("checkpoint_validation", checkpoint_node("validation"))
        workflow.add_node("checkpoint_export", checkpoint_node("export"))

        workflow.set_entry_point("entry")
        workflow.add_conditional_edges(
            "entry", _entry_route,
            {"research_planner": "research_planner", "acquisition": "acquisition", END: END},
        )
        workflow.add_conditional_edges("research_planner", _next_or_end("source_search"), {"source_search": "source_search", END: END})
        workflow.add_conditional_edges("source_search", _next_or_end("source_preview"), {"source_preview": "source_preview", END: END})
        workflow.add_conditional_edges("source_preview", _next_or_end("source_evaluator"), {"source_evaluator": "source_evaluator", END: END})
        workflow.add_conditional_edges("source_evaluator", _next_or_end("site_exploration"), {"site_exploration": "site_exploration", END: END})
        workflow.add_conditional_edges("site_exploration", _next_or_end("source_selector"), {"source_selector": "source_selector", END: END})
        workflow.add_conditional_edges("source_selector", _next_or_end("checkpoint_sources"), {"checkpoint_sources": "checkpoint_sources", END: END})
        workflow.add_conditional_edges("checkpoint_sources", _next_or_end("dataset_schema_designer"), {"dataset_schema_designer": "dataset_schema_designer", END: END})
        workflow.add_conditional_edges(
            "dataset_schema_designer", _schema_route, {"acquisition": "acquisition", END: END},
        )
        workflow.add_conditional_edges("acquisition", _next_or_end("checkpoint_acquisition"), {"checkpoint_acquisition": "checkpoint_acquisition", END: END})
        workflow.add_conditional_edges("checkpoint_acquisition", _next_or_end("processing"), {"processing": "processing", END: END})
        workflow.add_conditional_edges(
            "processing", _next_or_end("checkpoint_processing"),
            {"checkpoint_processing": "checkpoint_processing", END: END},
        )
        workflow.add_conditional_edges("checkpoint_processing", _processing_route, {"chunking": "chunking", "classification": "classification", END: END})
        workflow.add_conditional_edges("chunking", _next_or_end("checkpoint_chunking"), {"checkpoint_chunking": "checkpoint_chunking", END: END})
        workflow.add_conditional_edges("checkpoint_chunking", _next_or_end("extraction_router"), {"extraction_router": "extraction_router", END: END})
        workflow.add_conditional_edges("extraction_router", _next_or_end("structured_extraction"), {"structured_extraction": "structured_extraction", END: END})
        workflow.add_conditional_edges("structured_extraction", _next_or_end("checkpoint_extraction"), {"checkpoint_extraction": "checkpoint_extraction", END: END})
        workflow.add_conditional_edges("checkpoint_extraction", _next_or_end("field_evidence"), {"field_evidence": "field_evidence", END: END})
        workflow.add_conditional_edges("field_evidence", _next_or_end("evidence_validation"), {"evidence_validation": "evidence_validation", END: END})
        workflow.add_conditional_edges("evidence_validation", _next_or_end("quality_gate"), {"quality_gate": "quality_gate", END: END})
        workflow.add_conditional_edges("quality_gate", _next_or_end("record_resolution"), {"record_resolution": "record_resolution", END: END})
        workflow.add_conditional_edges("record_resolution", _next_or_end("classification"), {"classification": "classification", END: END})
        workflow.add_conditional_edges("classification", _next_or_end("metadata_enrichment"), {"metadata_enrichment": "metadata_enrichment", END: END})
        workflow.add_conditional_edges("metadata_enrichment", _next_or_end("entity_extraction"), {"entity_extraction": "entity_extraction", END: END})
        workflow.add_conditional_edges("entity_extraction", _next_or_end("relation_extraction"), {"relation_extraction": "relation_extraction", END: END})
        workflow.add_conditional_edges("relation_extraction", _next_or_end("quality_analysis"), {"quality_analysis": "quality_analysis", END: END})
        workflow.add_conditional_edges("quality_analysis", _next_or_end("normalization"), {"normalization": "normalization", END: END})
        workflow.add_conditional_edges("normalization", _next_or_end("validation"), {"validation": "validation", END: END})
        workflow.add_conditional_edges("validation", _next_or_end("checkpoint_validation"), {"checkpoint_validation": "checkpoint_validation", END: END})
        workflow.add_conditional_edges("checkpoint_validation", _next_or_end("deduplication"), {"deduplication": "deduplication", END: END})
        workflow.add_conditional_edges("deduplication", _next_or_end("export"), {"export": "export", END: END})
        workflow.add_edge("export", "storage")
        workflow.add_conditional_edges("storage", _next_or_end("checkpoint_export"), {"checkpoint_export": "checkpoint_export", END: END})
        workflow.add_edge("checkpoint_export", "manifest")
        workflow.add_edge("manifest", END)
        self._graph = workflow.compile()

    def invoke(self, state: AgentState) -> AgentState:
        return self._graph.invoke(state)

    @staticmethod
    def _safe_review_name(state: AgentState) -> str:
        raw_name = state.get("dataset_name") or state["domain"]
        return re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._") or state["domain"]

    def review_schema_path(self, state: AgentState) -> Path:
        return Path("knowledge/review") / f"{self._safe_review_name(state)}_draft_schema.json"

    def review_state_path(self, state: AgentState) -> Path:
        return Path("knowledge/review") / f"{self._safe_review_name(state)}_pipeline_state.json"

    def write_draft_review_file(self, state: AgentState) -> Path:
        """Persist both the editable schema and resumable pending pipeline state."""
        if state.get("status") != "waiting_for_schema_approval":
            raise ValueError("A draft schema can be written only while approval is pending.")
        review_dir = self.review_schema_path(state).parent
        review_dir.mkdir(parents=True, exist_ok=True)
        review_path = self.review_schema_path(state)
        review_path.write_text(
            json.dumps(state["draft_dataset_schema"], ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.review_state_path(state).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return review_path

    def load_pending_review_state(
        self,
        domain: str,
        dataset_name: str = "",
        config: Dict[str, Any] | None = None,
    ) -> AgentState:
        """Load an approval or stage checkpoint without repeating completed work."""
        identity = {"domain": domain, "dataset_name": dataset_name}
        state_path = self.review_state_path(identity)  # type: ignore[arg-type]
        if state_path.is_file():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        else:
            from src.core.checkpoint import load_checkpoint
            state = load_checkpoint({**identity, "config": config or {}})
        if state.get("domain") != domain:
            raise ValueError("The saved pipeline checkpoint belongs to a different domain.")
        if state.get("status") == "waiting_for_schema_approval":
            return state
        if not state.get("resume_from"):
            raise ValueError("The saved pipeline state is not a resumable checkpoint for this domain.")
        return state

    def approve_schema(self, state: AgentState, schema: Dict[str, Any] | None = None) -> AgentState:
        """Validate and approve a draft, then resume the same pipeline from acquisition."""
        if state.get("approved_dataset_schema"):
            return state
        if state.get("status") != "waiting_for_schema_approval":
            raise ValueError("Schema approval is available only while the pipeline is waiting for approval.")
        draft = DraftDatasetSchema.model_validate(schema or state.get("draft_dataset_schema"))
        _validate_draft_schema(draft)
        approved = ApprovedDatasetSchema(
            **draft.model_dump(by_alias=True),
            schema_version=1,
            approved_at=datetime.now(timezone.utc).isoformat(),
        )
        logger.info("Schema approved by user; resuming pipeline from acquisition.")
        resumed_state = {**state, "approved_dataset_schema": approved.model_dump(by_alias=True), "status": "schema_approved", "pipeline_status": "schema_approved"}
        return self.invoke(resumed_state)

    @staticmethod
    def cancel(state: AgentState) -> AgentState:
        return {**state, "status": "cancelled", "pipeline_status": "cancelled"}


def build_phase2_pipeline() -> DatasetGenerationPipeline:
    """Build the project's sole orchestration graph."""
    return DatasetGenerationPipeline()
