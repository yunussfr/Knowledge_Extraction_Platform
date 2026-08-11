"""Remove duplicate accepted structured records before export."""

import json
from typing import Any, Dict

from src.state.state import AgentState


def deduplication_node(state: AgentState) -> Dict[str, Any]:
    """Keeps the first record for identical extracted data and records rejections."""
    try:
        accepted_records = state.get("accepted_records", [])
        if not accepted_records:
            return {"status": "exporting", "pipeline_status": "exporting"}

        unique_records = []
        seen_data = set()
        rejected_records = list(state.get("rejected_records", []))
        for record in accepted_records:
            fingerprint = json.dumps(record.get("data", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if fingerprint in seen_data:
                rejected_records.append({
                    "source_url": record.get("_metadata", {}).get("source_url", ""),
                    "reasons": ["Duplicate extracted record."],
                })
                continue
            seen_data.add(fingerprint)
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
