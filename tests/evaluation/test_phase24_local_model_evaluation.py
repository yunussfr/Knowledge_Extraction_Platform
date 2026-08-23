from scripts.run_phase24_local_model_evaluation import run_local_model_benchmark


def test_phase24_without_backend_is_explicitly_unavailable():
    result = run_local_model_benchmark()

    assert result["status"] == "unavailable"
    assert result["local_first_enabled"] is False


def test_phase24_harness_scores_injected_provider_on_frozen_gold():
    class FixtureProvider:
        provider_name = "fixture-local"

        def generate(self, *, user_prompt, output_model, **_):
            page_id = user_prompt.split("Page ID: ", 1)[1].split("\n", 1)[0]
            source_url = user_prompt.split("Source URL: ", 1)[1].split("\n", 1)[0]
            fixture_records = {
                "single_record_page": [("Solaris Engine", "a compact inference runtime", "runtime")],
                "many_record_page": [
                    ("Alpha Model", "optimized for classification", "model"),
                    ("Beta Model", "designed for summarization", "model"),
                    ("Gamma Model", "supports multilingual retrieval", "model"),
                ],
                "repeated_dom_cards": [
                    ("Red Adapter", "connects legacy inputs", "adapter"),
                    ("Blue Adapter", "connects streaming inputs", "adapter"),
                    ("Green Adapter", "connects batch inputs", "adapter"),
                ],
                "table_page": [
                    ("Mercury Index", "provides dense lookup", "index"),
                    ("Venus Index", "provides sparse lookup", "index"),
                ],
                "long_prose_page": [("Atlas Retriever", "a fault-tolerant semantic retrieval service", "retrieval")],
                "missing_optional_page": [("Orbit Parser", "a Unicode-safe document parser", None)],
                "duplicate_information_page": [("Orion Store", "a versioned feature store", "storage")],
            }
            records = []
            for index, (name, description, category) in enumerate(fixture_records.get(page_id, []), 1):
                data = {"item_name": name, "description": description}
                evidence = {
                    "item_name": [{"source_url": source_url, "chunk_id": "fixture", "evidence_text": name}],
                    "description": [{"source_url": source_url, "chunk_id": "fixture", "evidence_text": description}],
                }
                if category is not None:
                    data["category"] = category
                    evidence["category"] = [{
                        "source_url": source_url,
                        "chunk_id": "fixture",
                        "evidence_text": f"Category: {category}",
                    }]
                records.append({
                    "local_record_id": f"{page_id}:{index}",
                    "data": data,
                    "confidence": 1.0,
                    "field_confidence": {field: 1.0 for field in data},
                    "field_evidence": evidence,
                })
            return output_model(records=records)

    result = run_local_model_benchmark(FixtureProvider())

    assert result["status"] == "completed"
    assert result["provider"] == "fixture-local"
    assert result["metrics"]["record_recall"] == 1.0
    assert result["metrics"]["schema_valid_rate"] == 1.0
    assert result["local_first_enabled"] is False
