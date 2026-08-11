from typing import Any, Dict

from src.agents.prompts import DATASET_SCHEMA_DESIGNER_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import DatasetSchemaField, DraftDatasetSchema
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def dataset_schema_designer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        logger.info("Designing draft dataset schema.")
        schema_config = state.get("config", {}).get("schema", {})
        fields = schema_config.get("fields")
        if fields is None and settings.data_source_provider != "mock":
            user_prompt = (
                f"Dataset topic: {state.get('dataset_topic', '')}\n"
                f"Dataset purpose: {state.get('dataset_purpose', '')}\n"
                f"Research plan: {state.get('research_plan', {})}\n"
                f"User schema constraints: {schema_config.get('constraints', '')}"
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
