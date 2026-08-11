"""Validate evidence-backed records against the approved dynamic schema."""

from typing import Any, Dict

from src.core.settings import settings
from src.schemas.models import ApprovedDatasetSchema
from src.state.state import AgentState


def _matches_type(value: Any, field_type: str) -> bool:
    if field_type.startswith("array["):
        if not isinstance(value, list):
            return False
        item_type = field_type[6:-1]
        return all(_matches_type(item, item_type) for item in value)
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    return checks[field_type](value)


def _validate_extracted_data(data: Dict[str, Any], schema: ApprovedDatasetSchema) -> list[str]:
    errors: list[str] = []
    for field in schema.fields:
        value = data.get(field.field_name)
        if value is None:
            if field.required and not field.nullable:
                errors.append(f"Missing required field: {field.field_name}")
            continue
        expected_type = field.type if field.type.startswith("array[") else ("array" if field.is_array else field.type)
        if not _matches_type(value, expected_type):
            errors.append(f"Field {field.field_name} must be {expected_type}.")
    return errors


def validation_node(state: AgentState) -> Dict[str, Any]:
    """Rejects low-confidence or schema-invalid structured records."""
    try:
        enriched_data = state.get("enriched_data", [])
        approved = state.get("approved_dataset_schema")
        schema = ApprovedDatasetSchema.model_validate(approved) if approved else None
        threshold = state.get("config", {}).get("quality", {}).get("minimum_confidence", settings.minimum_confidence)
        validated_data = []
        accepted_records = []
        rejected_records = list(state.get("rejected_records", []))
        report_details = []

        for item in enriched_data:
            validated_item = item.copy()
            record_errors: list[str] = []
            confidence = float(item.get("metadata", {}).get("confidence_score", 0.0))
            low_confidence = False
            if schema:
                if not item.get("cleaned_content", "").strip():
                    record_errors.append("Source content is empty.")
                record_errors.extend(_validate_extracted_data(item.get("extracted_data", {}), schema))
                if confidence < threshold:
                    record_errors.append(f"Confidence {confidence:.2f} is below the minimum {threshold:.2f}.")
                    low_confidence = True
            if record_errors:
                action = state.get("config", {}).get("quality", {}).get("low_confidence_action", settings.low_confidence_action)
                status = "review" if low_confidence and action == "review" else "rejected"
                validated_item["validation_status"] = status
                rejected_records.append({"source_url": item.get("source", ""), "status": status, "reasons": record_errors})
                report_details.append({"source": item.get("source"), "status": status, "reasons": record_errors})
                continue

            validated_item["validation_status"] = "validated"
            metadata = validated_item.setdefault("metadata", {})
            if schema:
                metadata["validation_method"] = "schema_and_confidence"
            else:
                # Preserve the legacy mock pipeline contract; real-source confidence
                # is always produced by structured_extraction_node above.
                metadata.setdefault("confidence_score", 0.95)
                metadata["validation_method"] = "rule_based"
            validated_data.append(validated_item)
            if schema:
                accepted_records.append({
                    "data": item.get("extracted_data", {}),
                    "_metadata": item.get("metadata", {}),
                })
            report_details.append({"source": item.get("source"), "status": "passed"})

        return {
            "validated_data": validated_data,
            "accepted_records": accepted_records,
            "rejected_records": rejected_records,
            "validation_report": {
                "details": report_details,
                "summary": f"Validated {len(validated_data)} records; rejected {len(rejected_records)} records.",
            },
            "status": "exporting",
            "pipeline_status": "exporting",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "validation", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
