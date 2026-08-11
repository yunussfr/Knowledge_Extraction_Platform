"""Write validated records using the project's existing dataset output location."""

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict

from src.core.settings import settings
from src.schemas.models import KnowledgeRecord, MetadataSchema
from src.state.state import AgentState


def _legacy_records(state: AgentState) -> list[dict[str, Any]]:
    records = []
    for index, item in enumerate(state.get("validated_data", []), start=1):
        metadata = MetadataSchema(
            schema_version="1.0",
            source_url=item["metadata"].get("source_url", ""),
            source_type="web",
            retrieved_at=item["metadata"].get("extracted_at", ""),
            processed_at=datetime.datetime.utcnow().isoformat(),
            confidence_score=item["metadata"].get("confidence_score", 0.0),
            validation_method=item["metadata"].get("validation_method", "rule_based"),
        )
        record = KnowledgeRecord(
            id=f"{state.get('domain', 'unknown')}-{uuid.uuid4().hex[:6]}",
            domain=state.get("domain", "unknown"),
            title=f"Extracted Knowledge {index}",
            content=item.get("normalized_content", item.get("cleaned_content", "")),
            relations=[relation.get("target_entity") for relation in item.get("relations", [])],
            tags=[item.get("category", "general")],
            metadata=metadata,
            validation_status=item.get("validation_status", "validated"),
        )
        records.append(record.model_dump())
    return records


def export_node(state: AgentState) -> Dict[str, Any]:
    """Exports dynamic records as JSON or JSONL and preserves the legacy format."""
    try:
        domain = state.get("domain", "unknown")
        dataset_name = state.get("dataset_name") or f"{domain}_latest"
        output_config = state.get("config", {}).get("output", {})
        output_format = output_config.get("format", settings.default_output_format).lower()
        if output_format not in {"json", "jsonl"}:
            raise ValueError(f"Unsupported output format: {output_format}")

        records = state.get("accepted_records") if state.get("approved_dataset_schema") else _legacy_records(state)
        output_dir = Path(output_config.get("directory", settings.output_directory))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{dataset_name}.{output_format}"
        if output_format == "jsonl":
            with output_path.open("w", encoding="utf-8") as file:
                for record in records:
                    file.write(json.dumps(record, ensure_ascii=False) + "\n")
        else:
            with output_path.open("w", encoding="utf-8") as file:
                json.dump(records, file, ensure_ascii=False, indent=2)

        save_raw = output_config.get("save_raw_content", settings.save_raw_content)
        save_clean = output_config.get("save_clean_content", settings.save_clean_content)
        if save_raw:
            (output_dir / f"{dataset_name}_raw.json").write_text(
                json.dumps(state.get("raw_data", []), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        if save_clean:
            (output_dir / f"{dataset_name}_clean.json").write_text(
                json.dumps(state.get("processed_data", []), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        return {
            "status": "completed",
            "pipeline_status": "completed",
            "validation_report": {**state.get("validation_report", {}), "output_path": str(output_path)},
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "export", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
