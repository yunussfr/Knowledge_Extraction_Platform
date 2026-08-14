"""Extract approved-schema records from cleaned source documents."""

from typing import Any, Dict, List

from src.agents.prompts import STRUCTURED_EXTRACTOR_SYSTEM_PROMPT
from src.core.logging import get_logger
from src.core.settings import settings
from src.core.tokenization import TokenCounter
from src.schemas.models import (
    ApprovedDatasetSchema,
    DocumentChunk,
    ExtractedRecord,
    ExtractionBatch,
    ExtractionResult,
)
from src.tools.structured_generation import get_structured_generation_provider


logger = get_logger(__name__)


def _mock_value(field_name: str, chunk: DocumentChunk) -> Any:
    if field_name in {"content", "text", "description"}:
        return chunk.content
    if field_name == "title":
        return chunk.source_title or chunk.source_metadata.get("title", "")
    return None


def _mock_extraction(chunk: DocumentChunk, schema: ApprovedDatasetSchema) -> ExtractionBatch:
    data: Dict[str, Any] = {}
    field_confidence: Dict[str, float] = {}
    for field in schema.fields:
        value = _mock_value(field.field_name, chunk)
        if value is not None:
            data[field.field_name] = value
            field_confidence[field.field_name] = 0.9
    confidence = min(field_confidence.values(), default=0.0)
    configured_records = chunk.source_metadata.get("mock_extraction_records")
    raw_records = configured_records if isinstance(configured_records, list) else [data]
    records = [ExtractedRecord(
        local_record_id=f"{chunk.chunk_id}:record:{index:04d}",
        source_url=chunk.source_url,
        segment_id=chunk.chunk_id,
        chunk_id=chunk.chunk_id,
        source_chunk_id=chunk.chunk_id,
        data=record_data,
        confidence=confidence,
        field_confidence={
            field_name: field_confidence.get(field_name, confidence)
            for field_name, value in record_data.items()
            if value not in (None, "", [], {})
        },
        chunk_index=chunk.chunk_index,
        total_chunks=chunk.total_chunks,
        extraction_method="semantic",
    ) for index, record_data in enumerate(raw_records, start=1)]
    return ExtractionBatch(
        source_url=chunk.source_url,
        segment_id=chunk.chunk_id,
        chunk_id=chunk.chunk_id,
        records=records,
    )


def _normalize_batch(
    batch: ExtractionBatch, chunk: DocumentChunk, *, method: str = "semantic"
) -> ExtractionBatch:
    batch.source_url = chunk.source_url
    batch.segment_id = chunk.chunk_id
    batch.chunk_id = chunk.chunk_id
    for index, record in enumerate(batch.records, start=1):
        record.source_url = chunk.source_url
        record.segment_id = chunk.chunk_id
        record.chunk_id = chunk.chunk_id
        record.source_chunk_id = chunk.chunk_id
        record.chunk_index = chunk.chunk_index
        record.total_chunks = chunk.total_chunks
        record.extraction_method = method
        if not record.local_record_id or record.local_record_id.startswith("segment:record:"):
            record.local_record_id = f"{chunk.chunk_id}:record:{index:04d}"
        for evidence_refs in record.field_evidence.values():
            for evidence in evidence_refs:
                evidence.source_url = chunk.source_url
                evidence.chunk_id = chunk.chunk_id
    return batch


def _legacy_result(record: ExtractedRecord) -> Dict[str, Any]:
    """Temporary projection for pre-Phase-15 callers; canonical state uses batches."""
    return ExtractionResult(
        source_url=record.source_url,
        data=record.data,
        confidence=record.confidence,
        field_confidence=record.field_confidence,
        source_chunk_id=record.chunk_id,
        chunk_index=record.chunk_index,
        total_chunks=record.total_chunks,
        extraction_method=record.extraction_method,
    ).model_dump(mode="json")


def _deterministic_batches(state: Dict[str, Any]) -> List[ExtractionBatch]:
    raw_batches = state.get("deterministic_extraction_batches", [])
    if raw_batches:
        return [ExtractionBatch.model_validate(item) for item in raw_batches]
    # Resume compatibility for a Phase-14 checkpoint that predates ExtractionBatch.
    batches: List[ExtractionBatch] = []
    for index, raw_result in enumerate(
        state.get("deterministic_extraction_results", []), start=1
    ):
        legacy = ExtractionResult.model_validate(raw_result)
        record = ExtractedRecord(
            **legacy.model_dump(),
            local_record_id=f"{legacy.source_chunk_id or 'legacy'}:record:{index:04d}",
            segment_id=legacy.source_chunk_id,
            chunk_id=legacy.source_chunk_id,
        )
        batches.append(ExtractionBatch(
            source_url=legacy.source_url,
            segment_id=legacy.source_chunk_id,
            chunk_id=legacy.source_chunk_id,
            records=[record],
            warnings=["Adapted from a pre-Phase-15 deterministic extraction result."],
        ))
    return batches


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
        routes = state.get("extraction_routes", [])
        if routes:
            semantic_sources = {
                route.get("source_url", "")
                for route in routes
                if route.get("method") == "semantic"
            }
            raw_chunks = [
                chunk for chunk in raw_chunks
                if chunk.get("source_url", chunk.get("source", "")) in semantic_sources
            ]
        logger.info("Semantically extracting %d routed document chunks.", len(raw_chunks))
        batches = _deterministic_batches(state)
        errors = list(state.get("errors", []))
        extraction_warnings = list(state.get("extraction_warnings", []))
        for raw_chunk in raw_chunks:
            try:
                chunk = DocumentChunk.model_validate(raw_chunk)
                if settings.data_source_provider == "mock":
                    batch = _mock_extraction(chunk, schema)
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
                        "Required response shape: an object with records[] and warnings[]. "
                        "Each records[] item must contain local_record_id, data, confidence, "
                        "field_confidence, and field_evidence. Return zero, one, or every "
                        "distinct source-supported record; never cap the response to one record. "
                        "Each populated field must have field_evidence with source_url, chunk_id, "
                        "and evidence_text copied from the supplied chunk content. Never invent "
                        "evidence; omit unsupported optional values and omit a record whose required "
                        "value is unsupported. Each record confidence must be a number from 0 to 1.\n"
                        f"Chunk content:\n{chunk.content}"
                    )
                    batch = get_structured_generation_provider().generate(
                        system_prompt=STRUCTURED_EXTRACTOR_SYSTEM_PROMPT,
                        user_prompt=user_prompt,
                        output_model=ExtractionBatch,
                        task_name="structured_extraction",
                    )
                batch = _normalize_batch(batch, chunk)
                batches.append(batch)
                extraction_warnings.extend(batch.warnings)
            except Exception as error:
                errors.append({
                    "node": "structured_extraction",
                    "source_url": raw_chunk.get("source_url", raw_chunk.get("source", "")),
                    "chunk_id": raw_chunk.get("chunk_id"),
                    "error": str(error),
                })
        expected_work = bool(raw_chunks or state.get("extraction_routes"))
        if expected_work and not batches:
            return {"errors": errors, "status": "failed", "pipeline_status": "failed"}
        records = [record for batch in batches for record in batch.records]
        results = [_legacy_result(record) for record in records]
        logger.info(
            "Extraction completed with %d batches and %d records.", len(batches), len(records)
        )
        return {
            "extraction_batches": [batch.model_dump(mode="json") for batch in batches],
            "chunk_extraction_results": results,
            "extraction_results": results,
            "extraction_warnings": extraction_warnings,
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
