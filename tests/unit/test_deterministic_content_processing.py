"""Phase 13 deterministic Bronze-to-Silver content processing tests."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

from src.agents.nodes.processing_node import processing_node
from src.core.content_processing import normalize_evidence_content
from src.tools.web.models import AcquiredDocument


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "web"
EXTRACTION_GOLD = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "fixtures"
    / "extraction_gold.json"
)


def test_whitespace_is_normalized_without_changing_unicode():
    content = "  İstanbul’da\u00a0kahve   kültürü.  \r\n\r\n\r\n  İkinci   paragraf. "

    processed, removed = normalize_evidence_content(content)

    assert processed == "İstanbul’da kahve kültürü.\n\nİkinci paragraf."
    assert removed == 0


def test_markdown_headings_lists_tables_and_fenced_code_are_preserved():
    content = (
        "# Heading   \n\n"
        "- First item  \n  - Nested item\n\n"
        "| Name | Value |   \n| --- | --- |\n| A | 1 |\n\n"
        "```python\nvalue  =  1\n```"
    )

    processed, _ = normalize_evidence_content(content)

    assert "# Heading" in processed
    assert "- First item" in processed
    assert "  - Nested item" in processed
    assert "| Name | Value |" in processed
    assert "| --- | --- |" in processed
    assert "value  =  1" in processed


def test_only_obvious_short_boilerplate_lines_are_removed():
    content = (
        "Home Products Pricing Sign in Subscribe\n\n"
        "# Core Finding\n\n"
        "Home energy pricing changed after the measured intervention.\n\n"
        "Privacy Policy\n"
        "Copyright 2026 Example. All rights reserved."
    )

    processed, removed = normalize_evidence_content(content)

    assert "Home Products Pricing" not in processed
    assert "Privacy Policy" not in processed
    assert "All rights reserved" not in processed
    assert "# Core Finding" in processed
    assert "Home energy pricing changed" in processed
    assert removed == 3


def test_processing_is_idempotent():
    content = "Home\n\n# Evidence\n\nA   supported fact.\n\n\n"

    once, _ = normalize_evidence_content(content)
    twice, removed = normalize_evidence_content(once)

    assert twice == once
    assert removed == 0


def test_processing_node_keeps_bronze_raw_and_hash_separate_from_silver():
    url = "https://fixture.example/noisy"
    raw = "Home Products Pricing Sign in Subscribe\n\n# Finding\n\nRaw evidence."
    fit = "# Finding\n\nRaw evidence."
    bronze = AcquiredDocument(
        source_url=url,
        canonical_url=url,
        title="Noisy",
        domain="fixture.example",
        raw_markdown=raw,
        fit_markdown=fit,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        source_provider="crawl4ai",
        content_hash=sha256(raw.encode()).hexdigest(),
        success=True,
    )
    state = {
        "dataset_topic": "Evidence",
        "raw_data": [bronze.to_pipeline_document()],
        "acquired_documents": [bronze.model_dump(mode="json")],
        "config": {"processing": {"minimum_words": 5}},
        "errors": [],
    }

    result = processing_node(state)

    assert result["status"] == "processing"
    silver = result["processed_documents"][0]
    assert silver["raw_content"] == raw
    assert silver["processed_content"] == fit
    assert silver["content_hash"] == sha256(raw.encode()).hexdigest()
    assert silver["processed_content_hash"] == sha256(fit.encode()).hexdigest()
    assert state["acquired_documents"][0]["raw_markdown"] == raw
    assert result["processed_data"][0]["cleaned_content"] == fit


def test_thin_content_is_detected_but_preserved_for_later_quality_policy():
    result = processing_node({
        "dataset_topic": "Evidence",
        "raw_data": [{
            "source": "https://fixture.example/thin",
            "title": "Thin",
            "content": "One important fact.",
            "metadata": {},
        }],
        "config": {"processing": {"minimum_words": 10}},
        "errors": [],
    })

    assert result["status"] == "processing"
    assert result["processed_documents"][0]["content_status"] == "thin"
    assert result["processed_data"][0]["cleaned_content"] == "One important fact."
    assert result["content_processing_metrics"]["thin_documents"] == 1


def test_empty_page_is_visible_and_partial_batch_continues():
    result = processing_node({
        "dataset_topic": "Evidence",
        "raw_data": [
            {"source": "https://fixture.example/empty", "content": "   \n\n"},
            {"source": "https://fixture.example/good", "content": "Supported evidence remains."},
        ],
        "config": {"processing": {"minimum_words": 2}},
        "errors": [],
    })

    assert result["status"] == "processing"
    assert [item["content_status"] for item in result["processed_documents"]] == [
        "empty",
        "usable",
    ]
    assert [item["source"] for item in result["processed_data"]] == [
        "https://fixture.example/good"
    ]
    assert result["errors"][0]["source_url"] == "https://fixture.example/empty"


def test_all_empty_pages_fail_before_chunking():
    result = processing_node({
        "dataset_topic": "Evidence",
        "raw_data": [{"source": "https://fixture.example/empty", "content": ""}],
        "config": {},
        "errors": [],
    })

    assert result["status"] == "failed"
    assert result["content_processing_metrics"]["empty_documents"] == 1


def test_web_fixtures_preserve_required_structural_evidence():
    fixtures = {
        "headings_page.html": ["Main Heading", "Methods", "Limitations"],
        "lists_page.html": ["First supporting item", "Collect the observation"],
        "tables_page.html": ["Sample", "Value A", "Value B"],
        "turkish_unicode_page.html": ["İstanbul’da Kahve Kültürü", "öğütme"],
    }
    for fixture_name, evidence_values in fixtures.items():
        content = (FIXTURE_DIR / fixture_name).read_text(encoding="utf-8")
        processed, _ = normalize_evidence_content(content)
        for evidence in evidence_values:
            assert evidence in processed


def test_frozen_extraction_evidence_is_not_lost_by_processing():
    gold = json.loads(EXTRACTION_GOLD.read_text(encoding="utf-8"))

    for page in gold["pages"]:
        processed, _ = normalize_evidence_content(page["content"])
        for record in page["expected_records"]:
            for evidence_values in record["field_evidence"].values():
                for evidence in evidence_values:
                    assert evidence in processed, (page["page_id"], evidence)
