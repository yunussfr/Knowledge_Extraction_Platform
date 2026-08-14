"""Phase 14 routing tests over frozen structured and prose fixture shapes."""

from hashlib import sha256

import pytest

from src.agents.nodes.extraction_router_node import extraction_router_node
from src.agents.nodes.record_merge_node import record_merge_node
from src.agents.nodes.structured_extraction_node import structured_extraction_node
from src.core.settings import settings
from src.schemas.models import ExtractionResult
from src.tools.groq_client import GroqClient


SOURCE_URL = "https://fixtures.example/catalog/items"


def _approved_schema() -> dict:
    return {
        "name": "catalog_items",
        "description": "Catalog item records.",
        "fields": [
            {
                "field_name": "item_name",
                "type": "string",
                "required": True,
                "description": "The item name.",
                "extraction_instruction": "Extract the explicit item name.",
            },
            {
                "field_name": "description",
                "type": "string",
                "required": True,
                "description": "The item description.",
                "extraction_instruction": "Extract the explicit item description.",
            },
            {
                "field_name": "category",
                "type": "string",
                "required": False,
                "description": "The item category.",
                "extraction_instruction": "Extract the explicit category when present.",
            },
        ],
        "schema_version": 1,
        "approved_at": "2026-08-14T00:00:00+00:00",
        "approved_by": "user",
    }


def _state(content: str, *, html: str = "", router: dict | None = None) -> dict:
    digest = sha256(content.encode("utf-8")).hexdigest()
    state = {
        "approved_dataset_schema": _approved_schema(),
        "config": {"extraction": {"router": router or {}}},
        "document_chunks": [{
            "chunk_id": "source_001_chunk_001",
            "source_url": SOURCE_URL,
            "source_title": "Fixture catalog",
            "chunk_index": 0,
            "total_chunks": 1,
            "content": content,
            "token_count": max(1, len(content.split())),
            "source_metadata": {"source_provider": "crawl4ai"},
        }],
        "processed_documents": [{
            "source_url": SOURCE_URL,
            "title": "Fixture catalog",
            "raw_content": content,
            "processed_content": content,
            "content_hash": digest,
            "processed_content_hash": digest,
            "word_count": len(content.split()),
            "content_status": "usable",
            "source_metadata": {"source_provider": "crawl4ai"},
        }],
        "acquired_documents": [{
            "source_url": SOURCE_URL,
            "title": "Fixture catalog",
            "domain": "fixtures.example",
            "raw_markdown": content,
            "html": html,
            "retrieved_at": "2026-08-14T00:00:00+00:00",
            "source_provider": "crawl4ai",
            "content_hash": digest,
            "success": True,
        }] if html else [],
        "errors": [],
    }
    return state


def _dom_router(method: str) -> dict:
    selector = ".card" if method == "css" else "//section[contains(@class, 'card')]"
    child = (lambda value: value) if method == "css" else (lambda value: f".//{value}")
    return {
        "rules": [{
            "id": f"cards-{method}",
            "method": method,
            "url_pattern": r"/catalog/items$",
            "schema": {
                "name": "cards",
                "baseSelector": selector,
                "fields": [
                    {"name": "item_name", "selector": child("h2"), "type": "text"},
                    {"name": "description", "selector": child("p"), "type": "text"},
                    {
                        "name": "category",
                        "selector": child("span"),
                        "type": ["text", "regex"],
                        "pattern": r"Category:\s*(.+)",
                        "group": 1,
                    },
                ],
            },
        }]
    }


@pytest.mark.parametrize("method", ["css", "xpath"])
def test_repeated_dom_cards_use_crawl4ai_without_semantic_calls(method):
    html = (
        '<section class="card"><h2>Red Adapter</h2><p>connects legacy inputs</p>'
        '<span>Category: adapter</span></section>'
        '<section class="card"><h2>Blue Adapter</h2><p>connects streaming inputs</p>'
        '<span>Category: adapter</span></section>'
    )
    state = _state(
        "Red Adapter connects legacy inputs. Category: adapter. "
        "Blue Adapter connects streaming inputs. Category: adapter.",
        html=html,
        router=_dom_router(method),
    )

    result = extraction_router_node(state)

    assert result["status"] == "routing_extraction"
    assert result["extraction_routes"][0]["method"] == method, result
    assert result["extraction_routes"][0]["model_call_required"] is False
    assert [item["data"]["item_name"] for item in result["deterministic_extraction_results"]] == [
        "Red Adapter", "Blue Adapter"
    ]
    assert all(
        item["extraction_method"] == method
        for item in result["deterministic_extraction_results"]
    )


def test_regex_rule_extracts_one_complete_evidenced_record():
    content = "Solaris Engine is a compact inference runtime. Category: runtime."
    router = {
        "rules": [{
            "id": "solaris-regex",
            "method": "regex",
            "url_pattern": r"/catalog/items$",
            "patterns": {
                "item_name": r"Solaris Engine",
                "description": r"a compact inference runtime",
                "category": r"(?<=Category: )runtime",
            },
        }]
    }

    result = extraction_router_node(_state(content, router=router))

    assert result["extraction_routes"][0]["method"] == "regex", result
    assert result["deterministic_extraction_results"][0]["data"] == {
        "item_name": "Solaris Engine",
        "description": "a compact inference runtime",
        "category": "runtime",
    }


def test_complete_markdown_table_avoids_every_groq_call(monkeypatch):
    content = (
        "| Item | Description | Category |\n"
        "|---|---|---|\n"
        "| Mercury Index | provides dense lookup | index |\n"
        "| Venus Index | provides sparse lookup | index |"
    )
    state = _state(content)
    routed = extraction_router_node(state)
    calls = []

    def fail_if_called(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Semantic provider must not be called for a reliable table.")

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(GroqClient, "complete_json", fail_if_called)
    try:
        extracted = structured_extraction_node({**state, **routed})
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert calls == []
    assert routed["extraction_routes"][0]["method"] == "table"
    assert routed["extraction_routing_metrics"]["avoided_model_calls"] == 1
    assert [item["data"] for item in extracted["chunk_extraction_results"]] == [
        {
            "item_name": "Mercury Index",
            "description": "provides dense lookup",
            "category": "index",
        },
        {
            "item_name": "Venus Index",
            "description": "provides sparse lookup",
            "category": "index",
        },
    ]
    merged = record_merge_node({
        **state,
        **extracted,
        "chunk_extraction_results": extracted["chunk_extraction_results"],
    })
    assert all(item["extraction_methods"] == ["table"] for item in merged["merged_records"])


def test_prose_routes_to_one_semantic_call(monkeypatch):
    content = "Atlas Retriever is a fault-tolerant semantic retrieval service. Category: retrieval."
    state = _state(content)
    routed = extraction_router_node(state)
    calls = []

    def complete_json(_, system_prompt, user_prompt, output_model, **kwargs):
        calls.append(user_prompt)
        return output_model(
            data={
                "item_name": "Atlas Retriever",
                "description": "a fault-tolerant semantic retrieval service",
                "category": "retrieval",
            },
            confidence=0.9,
        )

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(GroqClient, "complete_json", complete_json)
    try:
        extracted = structured_extraction_node({**state, **routed})
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert routed["extraction_routes"][0]["method"] == "semantic"
    assert len(calls) == 1
    assert extracted["chunk_extraction_results"][0]["extraction_method"] == "semantic"


def test_failed_explicit_selector_records_fallback_and_uses_semantic(monkeypatch):
    content = "Orbit Parser is a Unicode-safe document parser."
    html = "<main><p>Orbit Parser is a Unicode-safe document parser.</p></main>"
    router = _dom_router("css")
    router["rules"][0]["schema"]["baseSelector"] = ".missing-card"
    state = _state(content, html=html, router=router)

    routed = extraction_router_node(state)

    assert routed["extraction_routes"][0]["method"] == "semantic"
    assert routed["extraction_routes"][0]["fallback_from"] == "css"
    assert routed["extraction_routes"][0]["rule_id"] == "cards-css"
    assert routed["extraction_routing_metrics"]["fallback_sources"] == 1
