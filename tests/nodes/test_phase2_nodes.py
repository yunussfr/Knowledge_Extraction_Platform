"""
Phase 2 Node Unit Tests

Tests all Phase 2 Document Intelligence nodes in isolation.
No real LLM/API calls — mock state data only (per 09_TESTING_GUIDE).
"""

import pytest
from src.agents.nodes.classification_node import classification_node
from src.agents.nodes.metadata_enrichment_node import metadata_enrichment_node
from src.agents.nodes.entity_extraction_node import entity_extraction_node
from src.agents.nodes.relation_extraction_node import relation_extraction_node
from src.agents.nodes.quality_analysis_node import quality_analysis_node
from src.agents.nodes.normalization_node import normalization_node


# ---------------------------------------------------------------------------
# Shared mock state factory
# ---------------------------------------------------------------------------

def _mock_processed_item(content: str = "John Smith visited Istanbul last year.") -> dict:
    return {"source": "https://mock.test/doc", "cleaned_content": content}


def _mock_classified_item(**kwargs) -> dict:
    base = _mock_processed_item()
    base.update({"doc_type": "text", "category": "general"})
    base.update(kwargs)
    return base


def _mock_enriched_item() -> dict:
    item = _mock_classified_item()
    item["entities"] = [
        {"name": "John Smith", "type": "PERSON", "attributes": {}},
        {"name": "Istanbul", "type": "LOCATION", "attributes": {}},
    ]
    item["relations"] = []
    item["metadata"] = {
        "source_url": "https://mock.test/doc",
        "source_type": "text",
        "word_count": 7,
        "language": "en",
        "confidence_score": 0.0,
        "validation_method": "rule_based",
    }
    return item


# ---------------------------------------------------------------------------
# classification_node tests
# ---------------------------------------------------------------------------

class TestClassificationNode:
    def test_classifies_plain_text(self):
        state = {
            "processed_data": [_mock_processed_item()],
            "config": {"categories": ["culture", "history"]},
            "errors": [],
        }
        result = classification_node(state)
        assert "classified_data" in result
        assert result["classified_data"][0]["doc_type"] == "text"
        assert result["status"] == "enriching"

    def test_classifies_html_content(self):
        state = {
            "processed_data": [_mock_processed_item("<html><body>Hello</body></html>")],
            "config": {},
            "errors": [],
        }
        result = classification_node(state)
        assert result["classified_data"][0]["doc_type"] == "html"

    def test_empty_processed_data(self):
        state = {"processed_data": [], "config": {}, "errors": []}
        result = classification_node(state)
        assert result["classified_data"] == []
        assert result["status"] == "enriching"


# ---------------------------------------------------------------------------
# metadata_enrichment_node tests
# ---------------------------------------------------------------------------

class TestMetadataEnrichmentNode:
    def test_adds_metadata_fields(self):
        state = {
            "classified_data": [_mock_classified_item()],
            "errors": [],
        }
        result = metadata_enrichment_node(state)
        assert "enriched_data" in result
        meta = result["enriched_data"][0]["metadata"]
        assert "word_count" in meta
        assert "language" in meta
        assert "enriched_at" in meta

    def test_detects_turkish_language(self):
        state = {
            "classified_data": [_mock_classified_item(cleaned_content="Türkiye çok güzel bir ülke.")],
            "errors": [],
        }
        result = metadata_enrichment_node(state)
        assert result["enriched_data"][0]["metadata"]["language"] == "tr"


# ---------------------------------------------------------------------------
# entity_extraction_node tests
# ---------------------------------------------------------------------------

class TestEntityExtractionNode:
    def test_extracts_capitalized_entities(self):
        state = {
            "enriched_data": [_mock_enriched_item()],
            "config": {},
            "errors": [],
        }
        result = entity_extraction_node(state)
        entities = result["enriched_data"][0]["entities"]
        assert isinstance(entities, list)

    def test_applies_config_type_mapping(self):
        item = _mock_enriched_item()
        item["cleaned_content"] = "Ankara is the capital."
        state = {
            "enriched_data": [item],
            "config": {"entity_type_mappings": {"ankara": "CITY"}},
            "errors": [],
        }
        result = entity_extraction_node(state)
        entity_names = [e["name"].lower() for e in result["enriched_data"][0]["entities"]]
        entity_types = {e["name"].lower(): e["type"] for e in result["enriched_data"][0]["entities"]}
        if "ankara" in entity_names:
            assert entity_types["ankara"] == "CITY"


# ---------------------------------------------------------------------------
# relation_extraction_node tests
# ---------------------------------------------------------------------------

class TestRelationExtractionNode:
    def test_creates_co_occurrence_relations(self):
        state = {
            "enriched_data": [_mock_enriched_item()],
            "config": {},
            "errors": [],
        }
        result = relation_extraction_node(state)
        relations = result["enriched_data"][0]["relations"]
        assert isinstance(relations, list)
        assert len(relations) > 0  # Two entities → at least one relation

    def test_no_relations_for_single_entity(self):
        item = _mock_enriched_item()
        item["entities"] = [{"name": "Solo", "type": "UNKNOWN", "attributes": {}}]
        state = {"enriched_data": [item], "config": {}, "errors": []}
        result = relation_extraction_node(state)
        assert result["enriched_data"][0]["relations"] == []


# ---------------------------------------------------------------------------
# quality_analysis_node tests
# ---------------------------------------------------------------------------

class TestQualityAnalysisNode:
    def test_adds_quality_report(self):
        state = {
            "enriched_data": [_mock_enriched_item()],
            "config": {"quality": {"min_words": 5, "min_quality_score": 0.3}},
            "errors": [],
        }
        result = quality_analysis_node(state)
        qr = result["enriched_data"][0]["quality_report"]
        assert "overall_quality_score" in qr
        assert "passed" in qr

    def test_empty_content_scores_zero(self):
        item = _mock_enriched_item()
        item["cleaned_content"] = ""
        state = {"enriched_data": [item], "config": {}, "errors": []}
        result = quality_analysis_node(state)
        assert result["enriched_data"][0]["quality_report"]["content_score"] == 0.0


# ---------------------------------------------------------------------------
# normalization_node tests
# ---------------------------------------------------------------------------

class TestNormalizationNode:
    def test_collapses_whitespace(self):
        item = _mock_enriched_item()
        item["cleaned_content"] = "Hello   World\n\nTest"
        state = {"enriched_data": [item], "config": {}, "errors": []}
        result = normalization_node(state)
        assert result["enriched_data"][0]["normalized_content"] == "Hello World Test"

    def test_applies_custom_replacements(self):
        item = _mock_enriched_item()
        item["cleaned_content"] = "Dr. Smith"
        state = {
            "enriched_data": [item],
            "config": {"normalization": {"replacements": {"Dr.": "Doctor"}}},
            "errors": [],
        }
        result = normalization_node(state)
        assert "Doctor" in result["enriched_data"][0]["normalized_content"]

    def test_status_is_validating(self):
        state = {"enriched_data": [_mock_enriched_item()], "config": {}, "errors": []}
        result = normalization_node(state)
        assert result["status"] == "validating"
