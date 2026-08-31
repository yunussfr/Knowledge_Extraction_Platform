"""Deterministic identity normalization for knowledge upserts."""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any


def normalize_identity(value: Any) -> str:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def entity_identity(record: dict[str, Any], schema: dict[str, Any]) -> tuple[str, str, str]:
    data = dict(record.get("data", {}))
    metadata = dict(record.get("_metadata", {}))
    fields = list(schema.get("identity_fields") or [])
    if not fields:
        fields = [field.get("field_name") for field in schema.get("fields", []) if field.get("field_name") in {"id", "name", "title"}]
    values = [data.get(field) for field in fields if data.get(field) not in (None, "", [], {})]
    if values:
        canonical = " / ".join(str(value) for value in values)
        return "record_identity", canonical, normalize_identity(values if len(values) > 1 else values[0])
    local_id = str(record.get("local_record_id") or metadata.get("local_record_id") or record.get("source_url", "unknown"))
    return "record_identity", local_id, normalize_identity([record.get("source_url", ""), local_id])
