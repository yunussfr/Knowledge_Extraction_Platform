"""Extract approved-schema records from cleaned source documents."""

from typing import Any, Dict, List

from src.agents.prompts import STRUCTURED_EXTRACTOR_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.core.tokenization import TokenCounter
from src.schemas.models import ApprovedDatasetSchema, DocumentChunk, ExtractionResult
from src.tools.groq_client import GroqClient


logger = get_logger(__name__)


def _mock_value(field_name: str, chunk: DocumentChunk) -> Any:
    if field_name in {"content", "text", "description"}:
        return chunk.content
    if field_name == "title":
        return chunk.source_title or chunk.source_metadata.get("title", "")
    return None


def _mock_extraction(chunk: DocumentChunk, schema: ApprovedDatasetSchema) -> ExtractionResult:
    data: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    for field in schema.fields:
        value = _mock_value(field.field_name, chunk)
        if value is not None:
            data[field.field_name] = value
            field_confidence[field.field_name] = 0.9
    confidence = min(field_confidence.values(), default=0.0)
    return ExtractionResult(
        source_url=chunk.source_url,
        data=data,
        confidence=confidence,
        field_confidence=field_confidence,
        source_chunk_id=chunk.chunk_id,
        chunk_index=chunk.chunk_index,
        total_chunks=chunk.total_chunks,
    )


def _legacy_document_chunks(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Keep direct node callers compatible while the graph always uses chunking."""
    counter = TokenCounter()
    chunks = []
    for index, document in enumerate(state.get("processed_data", []), start=1):
        content = str(document.get("cleaned_content", "")).strip()
        if content:
            chunks.append(DocumentChunk(
                chunk_id=f"legacy_source_{index:03d}_chunk_001",
                source_url=document.get("source", ""),
                source_title=document.get("title", ""),
                chunk_index=0,
                total_chunks=1,
                content=content,
                token_count=max(1, counter.count(content)),
                source_metadata=dict(document.get("metadata", {})),
            ).model_dump())
    return chunks


def structured_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Runs only after approval and never uses a draft schema for extraction."""
    try:
        approved_schema = state.get("approved_dataset_schema")
        if not approved_schema:
            raise ValueError("An approved dataset schema is required before structured extraction.")
        schema = ApprovedDatasetSchema.model_validate(approved_schema)
        raw_chunks = state.get("document_chunks") or _legacy_document_chunks(state)
        logger.info("Extracting structured data from %d document chunks.", len(raw_chunks))
        results: List[Dict[str, Any]] = []
        errors = list(state.get("errors", []))
        for raw_chunk in raw_chunks:
            try:
                chunk = DocumentChunk.model_validate(raw_chunk)
                if settings.data_source_provider == "mock":
                    result = _mock_extraction(chunk, schema)
                else:
                    chunk_metadata = {
                        "chunk_id": chunk.chunk_id,
                        "chunk_index": chunk.chunk_index,
                        "total_chunks": chunk.total_chunks,
                        "heading": chunk.heading,
                        "source_url": chunk.source_url,
                        "source_title": chunk.source_title,
                        "source_metadata": chunk.source_metadata,
                    }
                    user_prompt = (
                        f"Approved dataset schema: {schema.model_dump(by_alias=True)}\n"
                        f"Chunk metadata: {chunk_metadata}\n"
                        "Required response keys: data, confidence, field_confidence. "
                        "The top-level confidence must be a number from 0 to 1.\n"
                        f"Chunk content:\n{chunk.content}"
                    )
                    result = GroqClient().complete_json(
                        STRUCTURED_EXTRACTOR_SYSTEM_PROMPT, user_prompt, ExtractionResult
                    )
                    result.source_url = chunk.source_url
                    result.source_chunk_id = chunk.chunk_id
                    result.chunk_index = chunk.chunk_index
                    result.total_chunks = chunk.total_chunks
                results.append(result.model_dump())
            except Exception as error:
                errors.append({
                    "node": "structured_extraction",
                    "source_url": raw_chunk.get("source_url", raw_chunk.get("source", "")),
                    "chunk_id": raw_chunk.get("chunk_id"),
                    "error": str(error),
                })
        if raw_chunks and not results:
            return {"errors": errors, "status": "failed", "pipeline_status": "failed"}
        logger.info("Structured extraction completed for %d chunks.", len(results))
        return {
            "chunk_extraction_results": results,
            "extraction_results": results,
            "errors": errors,
            "status": "extracting_data",
            "pipeline_status": "extracting_data",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "structured_extraction", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
