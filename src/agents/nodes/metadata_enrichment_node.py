import datetime
from typing import Dict, Any, List


def _build_enriched_metadata(item: Dict[str, Any], extraction: Dict[str, Any] | None, topic: str, schema_version: str) -> Dict[str, Any]:
    """Builds enriched metadata from item fields."""
    now = datetime.datetime.utcnow().isoformat()
    existing_meta = item.get("metadata", {})
    return {
        "source_url": item.get("source", ""),
        "source_type": item.get("doc_type", "text"),
        "source_title": item.get("title") or existing_meta.get("title", ""),
        "source_domain": existing_meta.get("source_domain", ""),
        "source_provider": existing_meta.get("source_provider", "mock"),
        "search_query": existing_meta.get("search_query", ""),
        "dataset_topic": topic,
        "extracted_at": existing_meta.get("extracted_at", now),
        "enriched_at": now,
        "schema_version": schema_version,
        "category": item.get("category", "general"),
        "language": _detect_language(item.get("cleaned_content", "")),
        "word_count": len(item.get("cleaned_content", "").split()),
        "confidence_score": (extraction or {}).get("confidence", existing_meta.get("confidence_score", 0.0)),
        "validation_method": existing_meta.get("validation_method", "rule_based"),
    }


def _detect_language(text: str) -> str:
    """Simple heuristic language detection (extensible via config)."""
    turkish_chars = set("çğışöüÇĞİŞÖÜ")
    if any(ch in turkish_chars for ch in text):
        return "tr"
    return "en"


def _enrich_item(item: Dict[str, Any], extraction: Dict[str, Any] | None, topic: str, schema_version: str) -> Dict[str, Any]:
    """Applies metadata enrichment to a single classified item."""
    enriched = item.copy()
    enriched["metadata"] = _build_enriched_metadata(item, extraction, topic, schema_version)
    if extraction:
        enriched["extracted_data"] = extraction.get("data", {})
        enriched["field_confidence"] = extraction.get("field_confidence", {})
    return enriched


def _enrich_merged_record(
    base_item: Dict[str, Any], merged: Dict[str, Any], topic: str, schema_version: str
) -> Dict[str, Any]:
    """Attach final provenance after compatible chunk extractions were merged."""
    extraction = {
        "data": merged.get("data", {}),
        "confidence": merged.get("confidence", 0.0),
        "field_confidence": merged.get("field_confidence", {}),
    }
    enriched = _enrich_item(base_item, extraction, topic, schema_version)
    metadata = enriched["metadata"]
    metadata["source_title"] = merged.get("source_title") or metadata.get("source_title", "")
    metadata["contributing_chunk_ids"] = merged.get("contributing_chunk_ids", [])
    metadata["merge_conflicts"] = merged.get("merge_conflicts", [])
    return enriched


def metadata_enrichment_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Enriches classified documents with structured metadata.
    Reads classified_data, adds language, word_count, enriched timestamps, category.
    """
    try:
        classified_data: List[Dict[str, Any]] = state.get("classified_data", [])

        print("Enriching metadata...")
        extraction_by_url = {
            result.get("source_url"): result for result in state.get("extraction_results", [])
        }
        schema_version = str(state.get("approved_dataset_schema", {}).get("schema_version", "1.0"))
        merged_records = state.get("merged_records", [])
        if merged_records:
            base_by_url = {item.get("source", ""): item for item in classified_data}
            enriched_data = []
            for merged in merged_records:
                source_url = merged.get("source_url", "")
                base_item = base_by_url.get(source_url, {
                    "source": source_url,
                    "title": merged.get("source_title", ""),
                    "cleaned_content": "",
                    "metadata": merged.get("source_metadata", {}),
                })
                enriched_data.append(_enrich_merged_record(
                    base_item, merged, state.get("dataset_topic", ""), schema_version
                ))
        else:
            enriched_data = [
                _enrich_item(item, extraction_by_url.get(item.get("source")), state.get("dataset_topic", ""), schema_version)
                for item in classified_data
            ]

        return {
            "enriched_data": enriched_data,
            "status": "enriching",
            "pipeline_status": "enriching",
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "metadata_enrichment", "error": str(e)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
