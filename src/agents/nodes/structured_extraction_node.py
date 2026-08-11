"""Extract approved-schema records from cleaned source documents."""

from typing import Any, Dict, List

from src.agents.prompts import STRUCTURED_EXTRACTOR_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.schemas.models import ApprovedDatasetSchema, ExtractionResult
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def _mock_value(field_name: str, document: Dict[str, Any]) -> Any:
    if field_name in {"content", "text", "description"}:
        return document.get("cleaned_content", "")
    if field_name == "title":
        return document.get("title") or document.get("metadata", {}).get("title", "")
    return None


def _mock_extraction(document: Dict[str, Any], schema: ApprovedDatasetSchema) -> ExtractionResult:
    data: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    for field in schema.fields:
        value = _mock_value(field.field_name, document)
        if value is not None:
            data[field.field_name] = value
            field_confidence[field.field_name] = 0.9
    confidence = min(field_confidence.values(), default=0.0)
    return ExtractionResult(source_url=document.get("source", ""), data=data, confidence=confidence, field_confidence=field_confidence)


def structured_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Runs only after approval and never uses a draft schema for extraction."""
    try:
        approved_schema = state.get("approved_dataset_schema")
        if not approved_schema:
            raise ValueError("An approved dataset schema is required before structured extraction.")
        schema = ApprovedDatasetSchema.model_validate(approved_schema)
        logger.info("Extracting structured data from %d cleaned documents.", len(state.get("processed_data", [])))
        results: List[Dict[str, Any]] = []
        for document in state.get("processed_data", []):
            if settings.data_source_provider == "mock":
                result = _mock_extraction(document, schema)
            else:
                user_prompt = (
                    f"Approved dataset schema: {schema.model_dump(by_alias=True)}\n"
                    f"Source URL: {document.get('source', '')}\n"
                    f"Source metadata: {document.get('metadata', {})}\n"
                    f"Clean source content:\n{document.get('cleaned_content', '')}"
                )
                result = GroqClient().complete_json(
                    STRUCTURED_EXTRACTOR_SYSTEM_PROMPT, user_prompt, ExtractionResult
                )
                result.source_url = document.get("source", "")
            results.append(result.model_dump())
        logger.info("Structured extraction completed for %d documents.", len(results))
        return {"extraction_results": results, "status": "extracting_data", "pipeline_status": "extracting_data"}
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "structured_extraction", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
