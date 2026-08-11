"""Remove duplicate accepted structured records before export."""

import json
from typing import Any, Dict

from src.state.state import AgentState


def _merge_duplicate_provenance(retained: Dict[str, Any], duplicate: Dict[str, Any]) -> None:
    """Retain evidence when identical final data is seen in another chunk/source."""
    retained_metadata = retained.setdefault("_metadata", {})
    duplicate_metadata = duplicate.get("_metadata", {})
    source_urls = list(retained_metadata.get("source_urls", []))
    for source_url in (retained_metadata.get("source_url", ""), duplicate_metadata.get("source_url", "")):
        if source_url and source_url not in source_urls:
            source_urls.append(source_url)
    if source_urls:
        retained_metadata["source_urls"] = source_urls
    retained_chunks = list(retained_metadata.get("contributing_chunk_ids", []))
    for chunk_id in duplicate_metadata.get("contributing_chunk_ids", []):
        if chunk_id not in retained_chunks:
            retained_chunks.append(chunk_id)
    if retained_chunks:
        retained_metadata["contributing_chunk_ids"] = retained_chunks


def deduplication_node(state: AgentState) -> Dict[str, Any]:
    """Remove identical final data while preserving all contributing provenance."""
    try:
        accepted_records = state.get("accepted_records", [])
        if not accepted_records:
            return {"status": "exporting", "pipeline_status": "exporting"}

        unique_records = []
        seen_data: Dict[str, Dict[str, Any]] = {}
        rejected_records = list(state.get("rejected_records", []))
        for record in accepted_records:
            fingerprint = json.dumps(record.get("data", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if fingerprint in seen_data:
                _merge_duplicate_provenance(seen_data[fingerprint], record)
                rejected_records.append({
                    "source_url": record.get("_metadata", {}).get("source_url", ""),
                    "reasons": ["Duplicate extracted record; provenance merged into the retained record."],
                })
                continue
            seen_data[fingerprint] = record
            unique_records.append(record)

        return {
            "accepted_records": unique_records,
            "rejected_records": rejected_records,
            "status": "exporting",
            "pipeline_status": "exporting",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "deduplication", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
