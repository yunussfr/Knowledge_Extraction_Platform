"""Unit tests for token-aware structural chunking."""

from src.agents.nodes.chunking_node import chunking_node
from src.core.tokenization import TokenCounter


def _state(content: str, target_tokens: int, overlap_tokens: int = 0) -> dict:
    return {
        "processed_data": [{
            "source": "https://example.test/long-document",
            "title": "Long document",
            "cleaned_content": content,
            "metadata": {"source_provider": "mock", "search_query": "example"},
        }],
        "config": {"extraction": {"chunking": {
            "enabled": True,
            "target_tokens": target_tokens,
            "overlap_tokens": overlap_tokens,
        }}},
        "errors": [],
    }


def test_small_document_remains_one_provenance_preserving_chunk():
    result = chunking_node(_state("A short source document.", target_tokens=100))

    assert result["status"] == "chunking"
    assert len(result["document_chunks"]) == 1
    chunk = result["document_chunks"][0]
    assert chunk["chunk_id"] == "source_001_chunk_001"
    assert chunk["source_url"] == "https://example.test/long-document"
    assert chunk["source_metadata"]["search_query"] == "example"
    assert chunk["total_chunks"] == 1


def test_heading_and_paragraph_boundaries_are_preserved_when_possible():
    counter = TokenCounter()
    first = "The first historical paragraph has supporting detail."
    second = "The second cultural paragraph has different supporting detail."
    target = max(counter.count(first), counter.count(second)) + 1
    result = chunking_node(_state(f"# History\n\n{first}\n\n# Culture\n\n{second}", target))

    chunks = result["document_chunks"]
    assert len(chunks) == 2
    assert chunks[0]["heading"] == "History"
    assert chunks[0]["content"] == first
    assert chunks[1]["heading"] == "Culture"
    assert chunks[1]["content"] == second


def test_large_single_section_is_split_within_the_token_budget():
    content = " ".join("This sentence contains several words." for _ in range(80))
    result = chunking_node(_state(content, target_tokens=30))

    chunks = result["document_chunks"]
    assert len(chunks) > 1
    assert all(chunk["token_count"] <= 30 for chunk in chunks)
    assert [chunk["chunk_index"] for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk["total_chunks"] == len(chunks) for chunk in chunks)


def test_adjacent_chunks_contain_bounded_overlap():
    sentence = "Alpha beta gamma."
    content = " ".join(sentence for _ in range(12))
    sentence_tokens = TokenCounter().count(sentence)
    result = chunking_node(_state(
        content,
        target_tokens=(sentence_tokens * 3) + 1,
        overlap_tokens=sentence_tokens,
    ))

    chunks = result["document_chunks"]
    assert len(chunks) > 1
    assert chunks[1]["overlap_token_count"] > 0
    assert chunks[0]["content"].endswith(sentence)
    assert chunks[1]["content"].startswith(sentence)


def test_token_counter_failure_is_recorded_with_source_provenance(monkeypatch):
    class FailingCounter:
        def count(self, text: str) -> int:
            raise RuntimeError("Tokenizer unavailable")

    monkeypatch.setattr("src.agents.nodes.chunking_node.TokenCounter", FailingCounter)
    result = chunking_node(_state("A source that cannot be counted.", target_tokens=10))

    assert result["status"] == "failed"
    assert result["errors"][0]["node"] == "chunking"
    assert result["errors"][0]["source_url"] == "https://example.test/long-document"
    assert result["errors"][0]["chunk_id"] is None
