"""Phase 20 ordered duplicate stages, safety, and provenance tests."""

from copy import deepcopy

from src.agents.nodes.deduplication_node import deduplication_node


def _schema() -> dict:
    return {
        "name": "deduplication",
        "description": "Staged deduplication fixtures.",
        "fields": [
            {
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "Item name.",
                "extraction_instruction": "Extract item name.",
            },
            {
                "field_name": "description",
                "type": "string",
                "required": True,
                "description": "Description.",
                "extraction_instruction": "Extract description.",
            },
            {
                "field_name": "category",
                "type": "string",
                "required": False,
                "nullable": True,
                "description": "Category.",
                "extraction_instruction": "Extract category.",
            },
        ],
        "identity_fields": ["item_name"],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _record(
    source_url: str,
    local_id: str,
    data: dict,
    *,
    quality: float = 0.8,
    content_hash: str = "",
) -> dict:
    chunk_id = f"{local_id}_chunk"
    return {
        "data": data,
        "_metadata": {
            "source_url": source_url,
            "source_urls": [source_url],
            "source_titles": {source_url: local_id},
            "source_content_hashes": (
                {source_url: content_hash} if content_hash else {}
            ),
            "contributing_chunk_ids": [chunk_id],
            "contributing_record_ids": [local_id],
            "contributors": [{
                "source_url": source_url,
                "local_record_id": local_id,
                "chunk_id": chunk_id,
                "extraction_method": "semantic",
            }],
            "field_evidence": {
                field_name: [{
                    "source_url": source_url,
                    "chunk_id": chunk_id,
                    "evidence_text": str(value).strip(),
                }]
                for field_name, value in data.items()
            },
            "evidence_quality_score": quality,
            "evidence_support_statuses": ["SUPPORTED"],
            "quality_assessments": [{
                "local_record_id": local_id,
                "source_url": source_url,
                "support_status": "SUPPORTED",
                "components": {},
                "final_quality_score": quality,
                "accepted": True,
                "reasons": [],
            }],
            "merge_conflicts": [],
        },
    }


def _run(records: list[dict]) -> dict:
    return deduplication_node({
        "approved_dataset_schema": _schema(),
        "accepted_records": records,
        "rejected_records": [],
        "errors": [],
    })


def test_canonical_url_or_content_hash_stage_runs_before_exact_record_stage():
    first = _record(
        "https://EXAMPLE.test:443/item#fragment",
        "first",
        {"item_name": "Alpha", "description": "Same record"},
        quality=0.7,
        content_hash="shared-hash",
    )
    stronger = _record(
        "https://mirror.test/item",
        "stronger",
        {"item_name": " alpha ", "description": "same   record"},
        quality=0.9,
        content_hash="shared-hash",
    )

    result = _run([first, stronger])

    assert result["deduplication_metrics"]["stage_counts"] == {
        "source_or_content": 1,
        "exact_normalized_record": 0,
        "schema_identity": 0,
    }
    retained = result["accepted_records"][0]
    assert retained["_metadata"]["source_url"] == "https://mirror.test/item"
    assert set(retained["_metadata"]["source_urls"]) == {
        "https://EXAMPLE.test:443/item#fragment",
        "https://mirror.test/item",
    }
    assert len(retained["_metadata"]["contributors"]) == 2
    assert len(retained["_metadata"]["field_evidence"]["item_name"]) == 2


def test_exact_normalized_record_stage_deduplicates_across_unrelated_sources():
    result = _run([
        _record(
            "https://one.test/item",
            "one",
            {"item_name": "Orbit Parser", "description": "Unicode   parser"},
            content_hash="hash-one",
        ),
        _record(
            "https://two.test/item",
            "two",
            {"description": "unicode parser", "item_name": " orbit parser "},
            content_hash="hash-two",
        ),
    ])

    assert len(result["accepted_records"]) == 1
    assert result["deduplication_metrics"]["stage_counts"]["exact_normalized_record"] == 1
    assert result["deduplication_metrics"]["remaining_exact_duplicate_rate"] == 0.0


def test_schema_identity_removes_only_compatible_subset_and_keeps_conflicts():
    subset = _record(
        "https://one.test/subset",
        "subset",
        {"item_name": "Atlas", "description": "Base description"},
    )
    superset = _record(
        "https://two.test/superset",
        "superset",
        {
            "item_name": " atlas ",
            "description": "base description",
            "category": "retrieval",
        },
    )
    conflict_a = _record(
        "https://one.test/conflict",
        "conflict-a",
        {"item_name": "Mercury", "description": "First description"},
    )
    conflict_b = _record(
        "https://two.test/conflict",
        "conflict-b",
        {"item_name": " mercury ", "description": "Second description"},
    )

    result = _run([subset, superset, conflict_a, conflict_b])

    assert len(result["accepted_records"]) == 3
    assert result["deduplication_metrics"]["stage_counts"]["schema_identity"] == 1
    assert result["deduplication_metrics"]["identity_conflicts_retained"] == 1
    atlas = next(
        record for record in result["accepted_records"]
        if record["data"]["item_name"].strip().casefold() == "atlas"
    )
    assert atlas["data"]["category"] == "retrieval"
    assert len(atlas["_metadata"]["contributors"]) == 2


def test_same_source_with_different_record_data_is_not_collapsed_by_source_stage():
    source_url = "https://same.test/catalog"
    result = _run([
        _record(source_url, "alpha", {
            "item_name": "Alpha", "description": "First"
        }, content_hash="same-page"),
        _record(source_url, "beta", {
            "item_name": "Beta", "description": "Second"
        }, content_hash="same-page"),
    ])

    assert len(result["accepted_records"]) == 2
    assert result["deduplication_metrics"]["duplicates_removed"] == 0


def test_staged_deduplication_is_idempotent():
    records = [
        _record("https://one.test/a", "a", {
            "item_name": "Alpha", "description": "Same"
        }),
        _record("https://two.test/a", "b", {
            "item_name": " alpha ", "description": "same"
        }),
    ]
    first = _run(deepcopy(records))
    second = deduplication_node({
        "approved_dataset_schema": _schema(),
        "accepted_records": deepcopy(first["accepted_records"]),
        "rejected_records": deepcopy(first["rejected_records"]),
        "errors": [],
    })

    assert second["accepted_records"] == first["accepted_records"]
    assert second["deduplication_metrics"]["duplicates_removed"] == 0
    assert second["deduplication_metrics"]["remaining_exact_duplicate_rate"] == 0.0
