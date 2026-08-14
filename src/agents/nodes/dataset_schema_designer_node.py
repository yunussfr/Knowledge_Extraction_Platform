import json
from typing import Any, Dict

from src.agents.prompts import DATASET_SCHEMA_DESIGNER_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.source_registry import normalize_candidate_url
from src.core.settings import settings
from src.schemas.models import (
    DatasetSchemaDesignerInput,
    DatasetSchemaField,
    DraftDatasetSchema,
    SchemaEvidencePreview,
)
from src.tools.web.models import SourcePreview
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def _canonical(url: str) -> str:
    try:
        return normalize_candidate_url(url)
    except ValueError:
        return url


def build_dataset_schema_designer_input(
    state: Dict[str, Any],
) -> DatasetSchemaDesignerInput:
    """Project only final selected previews into the schema-design boundary."""
    schema_config = state.get("config", {}).get("schema", {})
    if not isinstance(schema_config, dict):
        schema_config = {}
    raw_selections = state.get("source_selections") or [
        item.get("selection") or item for item in state.get("selected_sources", [])
    ]
    if not raw_selections:
        raise ValueError("Dataset schema design requires at least one final selected source.")

    preview_by_url: dict[str, SourcePreview] = {}
    for raw_preview in state.get("source_previews", []):
        preview = SourcePreview.model_validate(raw_preview)
        preview_by_url[_canonical(preview.url)] = preview

    selected_previews: list[SchemaEvidencePreview] = []
    seen_urls: set[str] = set()
    ordered_selections = sorted(
        raw_selections,
        key=lambda item: int(item.get("rank") or item.get("priority") or 1),
    )
    for fallback_rank, selection in enumerate(ordered_selections, start=1):
        url = str(selection.get("url", ""))
        canonical_url = _canonical(url)
        if not canonical_url or canonical_url in seen_urls:
            continue
        seen_urls.add(canonical_url)
        preview = preview_by_url.get(canonical_url)
        if preview is None or not preview.fetch_success:
            raise ValueError(
                f"Final selected source lacks a successful bounded preview: {url}"
            )
        selected_previews.append(SchemaEvidencePreview(
            **preview.model_dump(exclude={"internal_links", "external_links", "error"}),
            source_rank=int(
                selection.get("rank") or selection.get("priority") or fallback_rank
            ),
            selection_score=float(selection.get("selection_score", 0.0)),
        ))

    fields = schema_config.get("fields") or []
    return DatasetSchemaDesignerInput(
        dataset_topic=state.get("dataset_topic", ""),
        dataset_purpose=state.get("dataset_purpose", ""),
        research_plan=state.get("research_plan", {}),
        source_policy=state.get("source_policy") or {},
        selected_source_previews=selected_previews,
        user_schema_constraints=schema_config.get("constraints", ""),
        configured_fields=fields,
    )


def dataset_schema_designer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        logger.info("Designing draft dataset schema.")
        designer_input = build_dataset_schema_designer_input(state)
        schema_config = state.get("config", {}).get("schema", {})
        fields = schema_config.get("fields")
        if fields is None and settings.data_source_provider != "mock":
            user_prompt = json.dumps(
                {
                    "schema_designer_input": designer_input.model_dump(mode="json"),
                    "draft_dataset_schema_contract": DraftDatasetSchema.model_json_schema(),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            fields = [field.model_dump(by_alias=True) for field in GroqClient().complete_json(
                DATASET_SCHEMA_DESIGNER_SYSTEM_PROMPT, user_prompt, DraftDatasetSchema
            ).fields]
        fields = fields or [
            DatasetSchemaField(
                field_name="content", type="string", required=True, nullable=False,
                description="Source-backed knowledge text.",
                extraction_instruction="Extract the main factual content without adding information.",
            ).model_dump(by_alias=True)
        ]
        draft = DraftDatasetSchema(
            name=schema_config.get("name") or state.get("dataset_name") or f"{state.get('domain', 'dataset')}_dataset",
            description=state.get("dataset_purpose", "Structured dataset"),
            fields=fields,
        )
        # Dynamic datasets always require an explicit domain approval before scrape/extraction.
        status = "waiting_for_schema_approval"
        logger.info("Draft schema created with %d fields; waiting for user approval.", len(draft.fields))
        return {
            "schema_design_input": designer_input.model_dump(mode="json"),
            "draft_dataset_schema": draft.model_dump(by_alias=True),
            "status": status,
            "pipeline_status": status,
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "dataset_schema_designer", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
