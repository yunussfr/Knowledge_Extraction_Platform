"""Round-trip the frozen extraction gold through the Phase 15 batch contract."""

from __future__ import annotations

import json
from pathlib import Path

from src.evaluation import evaluate_extraction, load_json
from src.schemas.models import EvidenceRef, ExtractedRecord, ExtractionBatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests" / "evaluation" / "fixtures" / "extraction_gold.json"


def run_contract_benchmark() -> dict:
    """Measure contract capacity only; this is not a live model-quality claim."""
    gold = load_json(FIXTURE_PATH)
    predictions = []
    total_batches = 0
    for page in gold["pages"]:
        chunk_id = f"{page['page_id']}:chunk:001"
        records = []
        for expected in page["expected_records"]:
            records.append(ExtractedRecord(
                local_record_id=expected["record_id"],
                source_url=page["source_url"],
                segment_id=page["page_id"],
                chunk_id=chunk_id,
                source_chunk_id=chunk_id,
                data=expected["data"],
                confidence=1.0,
                field_confidence={field: 1.0 for field in expected["data"]},
                field_evidence={
                    field: [EvidenceRef(
                        source_url=page["source_url"],
                        chunk_id=chunk_id,
                        evidence_text=text,
                    ) for text in evidence]
                    for field, evidence in expected["field_evidence"].items()
                },
                extraction_method="semantic",
            ))
        batch = ExtractionBatch(
            source_url=page["source_url"],
            segment_id=page["page_id"],
            chunk_id=chunk_id,
            records=records,
        )
        total_batches += 1
        predictions.append({
            "page_id": page["page_id"],
            "records": [record.model_dump(mode="json") for record in batch.records],
        })
    return {
        "benchmark_version": "1.0",
        "benchmark": "phase15_contract_roundtrip",
        "note": "Contract capacity ceiling over frozen gold; not live provider quality.",
        "batch_count": total_batches,
        "metrics": evaluate_extraction(
            gold, {"extraction_predictions": predictions}
        ),
    }


def main() -> None:
    print(json.dumps(run_contract_benchmark(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
