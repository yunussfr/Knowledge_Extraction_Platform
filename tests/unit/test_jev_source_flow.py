"""Offline contract checks for the opt-in Jev source-evaluation path."""

from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import replace
from hashlib import sha256
import json

import pytest

from src.agents.nodes import source_evaluator_node as evaluator_module
from src.agents.nodes import source_profile_node as profile_module
from src.agents.graphs import phase2_pipeline
from src.core.settings import settings
from src.core.source_policy_evaluator import evaluate_source_for_policy
from src.schemas.models import SourcePolicy, SourceProfile, SourceProfileBatch
from src.tools.structured_generation.jev_provider import JevDecisionProvider
from src.tools.structured_generation.source_evaluation_provider import get_source_evaluation_provider
from src.tools.web.models import AcquiredDocument, SourcePreview
from src.tools.web.preview_builder import build_source_preview


URLS = ["https://example.com/a", "https://example.com/b"]
CHECKS = {"source_type_supported": .91, "content_supported": .92, "scores_supported": .93}


def _preview(url: str) -> dict:
    return SourcePreview(url=url, title="Evidence", domain="example.com",
                         relevant_text="Topic evidence and dataset purpose.",
                         preview_word_count=5, fetch_success=True).model_dump(mode="json")


def _state(count: int = 2) -> dict:
    return {"candidate_sources": [{"url": url, "candidate_id": f"cand_{index}"}
                                  for index, url in enumerate(URLS[:count], 1)],
            "source_previews": [_preview(url) for url in URLS[:count]],
            "dataset_topic": "Topic", "dataset_purpose": "Dataset purpose",
            "source_policy": {}, "config": {"research": {"max_sources": count}}, "errors": []}


def _profile() -> SourceProfile:
    return SourceProfile(source_type="dataset", authority_score=.8,
                         information_density_score=.8, technical_depth_score=.8,
                         extractability_score=.8, content_depth="deep")


class _FakeGenerator:
    def __init__(self, *, bad_url: str | None = None):
        self.bad_url = bad_url
        self.calls = []

    def generate(self, *, user_prompt, **_):
        candidates = json.loads(user_prompt)["candidates"]
        self.calls.append([item["url"] for item in candidates])
        return SourceProfileBatch.model_validate({"profiles": [
            {"url": item["url"], "candidate_id": item["candidate_id"],
             "source_profile": _profile().model_dump(mode="json")}
            for item in candidates if item["url"] != self.bad_url
        ]})


class _FakeJev:
    def __init__(self, *, reject_first: bool = False, fail: bool = False):
        self.verify_calls = 0
        self.score_calls = 0
        self.reject_first = reject_first
        self.fail = fail

    def verify_profile(self, *, preview, profile):
        self.verify_calls += 1
        if self.fail:
            raise ConnectionError("Jev unavailable")
        return {key: (.5 if self.reject_first and self.verify_calls == 1 else value)
                for key, value in CHECKS.items()}

    def score_relevance(self, *, preview, topic, purpose):
        self.score_calls += 1
        return .75, .95

    def metrics(self):
        return {"provider": "jev", "jev_calls": self.verify_calls + self.score_calls}


def test_preview_finds_late_passage_and_preserves_positions():
    words = ["filler"] * 500 + ["climate", "policy", "dataset"] * 100
    markdown = " ".join(words)
    doc = AcquiredDocument(source_url=URLS[0], canonical_url=URLS[0], title="Evidence",
        domain="example.com", raw_markdown=markdown, fit_markdown=markdown,
        retrieved_at=datetime.now(timezone.utc).isoformat(), source_provider="fixture",
        content_hash=sha256(markdown.encode()).hexdigest(), success=True)

    class Scorer:
        def score_passages(self, *, query, passages):
            return [10.0 if "climate" in passage else 0.0 for passage in passages]

    preview = build_source_preview(doc, max_words=400, query="climate policy", scorer=Scorer())
    assert preview.preview_word_count == 400
    assert len(preview.relevant_text.split()) == 400
    assert preview.selected_passage_ranges == sorted(preview.selected_passage_ranges)
    assert preview.selected_passage_ranges[-1][1] == 800
    assert "climate policy dataset" in preview.relevant_text
    for start, end in preview.selected_passage_ranges:
        assert " ".join(words[start:end]) in preview.relevant_text
    pruned = doc.model_copy(update={"fit_markdown": " ".join(words[:100])})
    from_pruned = build_source_preview(pruned, max_words=400, query="climate policy", scorer=Scorer())
    assert "climate policy dataset" in from_pruned.relevant_text
    assert from_pruned.selected_passage_ranges[-1][1] == 800


def test_profile_nodes_retry_per_candidate_and_groq_only_when_unsupported(monkeypatch):
    local = _FakeGenerator(bad_url=URLS[1])
    cloud = _FakeGenerator()
    jev = _FakeJev()
    monkeypatch.setattr(profile_module, "settings", replace(
        settings, source_evaluator_benchmark_approved=True,
        source_evaluation_batch_size=2))
    monkeypatch.setattr(profile_module, "OllamaStructuredProvider", lambda **_: local)
    monkeypatch.setattr(profile_module, "GroqStructuredProvider", lambda **_: cloud)
    monkeypatch.setattr(profile_module, "JevDecisionProvider", lambda: jev)
    state = _state()
    state.update(profile_module.source_profile_generation_node(state))
    assert [item["url"] for item in state["source_profile_proposals"]] == URLS
    assert state["source_profile_proposals"][0].get("source_profile")
    assert "error" in state["source_profile_proposals"][1]
    assert local.calls == [URLS, [URLS[0]], [URLS[1]]]
    state.update(profile_module.source_profile_verification_node(state))
    assert [item["status"] for item in state["source_profile_verifications"]] == ["accepted", "accepted"]
    assert [item["provider"] for item in state["source_profile_verifications"]] == ["ollama", "groq"]
    assert cloud.calls == [[URLS[1]]]
    assert state["source_profile_metrics"]["groq_fallback_calls"] == 1


def test_unsupported_profiles_reject_candidate_and_jev_outage_fails_node(monkeypatch):
    state = _state(1)
    state["source_profile_proposals"] = [{"url": URLS[0], "candidate_id": "cand_1",
        "source_profile": _profile().model_dump(mode="json")}]
    monkeypatch.setattr(profile_module, "GroqStructuredProvider", lambda **_: _FakeGenerator())
    monkeypatch.setattr(profile_module, "JevDecisionProvider", lambda: _FakeJev(reject_first=True))
    result = profile_module.source_profile_verification_node(state)
    assert result["source_profile_verifications"][0]["provider"] == "groq"
    assert result["source_profile_verifications"][0]["status"] == "accepted"
    monkeypatch.setattr(profile_module, "JevDecisionProvider", lambda: _FakeJev(fail=True))
    error = profile_module.source_profile_verification_node(state)
    assert error["status"] == "failed"
    assert "Jev unavailable" in error["errors"][-1]["error"]


def test_two_unsupported_profiles_reject_only_that_candidate(monkeypatch):
    state = _state()
    state["source_profile_proposals"] = [
        {"url": url, "candidate_id": f"cand_{index}",
         "source_profile": _profile().model_dump(mode="json")}
        for index, url in enumerate(URLS, 1)]
    class SelectiveJev(_FakeJev):
        def verify_profile(self, *, preview, profile):
            self.verify_calls += 1
            return {key: (.2 if preview.url == URLS[0] else value)
                    for key, value in CHECKS.items()}
    jev = SelectiveJev()
    cloud = _FakeGenerator()
    monkeypatch.setattr(profile_module, "GroqStructuredProvider", lambda **_: cloud)
    monkeypatch.setattr(profile_module, "JevDecisionProvider", lambda: jev)
    state.update(profile_module.source_profile_verification_node(state))
    assert state["status"] == "source_profiles_verified"
    assert [item["status"] for item in state["source_profile_verifications"]] == ["rejected", "accepted"]
    assert cloud.calls == [[URLS[0]]]
    monkeypatch.setattr(evaluator_module, "get_source_evaluation_provider", lambda: jev)
    evaluated, metrics, _ = evaluator_module._jev_evaluation(
        state, evaluator_module.build_source_evaluator_input(state))
    assert [item.decision for item in evaluated.evaluated_sources] == ["reject", "select"]
    assert jev.score_calls == 1
    assert metrics["profile_rejections"] == 1


def test_missing_groq_configuration_rejects_one_candidate(monkeypatch):
    state = _state()
    state["source_profile_proposals"] = [
        {"url": URLS[0], "candidate_id": "cand_1", "error": "Gemma unavailable"},
        {"url": URLS[1], "candidate_id": "cand_2",
         "source_profile": _profile().model_dump(mode="json")},
    ]
    monkeypatch.setattr(profile_module, "GroqStructuredProvider",
                        lambda **_: (_ for _ in ()).throw(ValueError("Groq key missing")))
    monkeypatch.setattr(profile_module, "JevDecisionProvider", lambda: _FakeJev())
    result = profile_module.source_profile_verification_node(state)
    assert result["status"] == "source_profiles_verified"
    assert [item["status"] for item in result["source_profile_verifications"]] == ["rejected", "accepted"]
    assert "Groq key missing" in result["source_profile_verifications"][0]["reasons"][-1]


def test_jev_score_uses_sixty_forty_and_preserves_hard_rejection(monkeypatch):
    state = _state(1)
    state["source_profile_verifications"] = [{"url": URLS[0], "candidate_id": "cand_1",
        "source_profile": _profile().model_dump(mode="json"), "status": "accepted",
        "provider": "ollama", "checks": CHECKS}]
    jev = _FakeJev()
    monkeypatch.setattr(evaluator_module, "get_source_evaluation_provider", lambda: jev)
    evaluation, metrics, _ = evaluator_module._jev_evaluation(
        state, evaluator_module.build_source_evaluator_input(state))
    item = evaluation.evaluated_sources[0]
    assert item.candidate_id == "cand_1"
    assert item.final_score == round(.6 * .75 + .4 * item.policy_alignment_score, 6)
    assert metrics["scoring_weights"] == {"topic_purpose": .6, "policy": .4}
    assert jev.score_calls == 1
    forbidden = evaluate_source_for_policy(url=URLS[0], profile=_profile(),
        topic_relevance_score=1, preview=SourcePreview.model_validate(_preview(URLS[0])),
        policy=SourcePolicy(), blocked_domains=["example.com"],
        relevance_weight=.6, policy_weight=.4)
    assert forbidden.hard_policy_rejected and forbidden.decision == "reject"


def test_profile_identity_and_jev_typed_answers(monkeypatch):
    state = _state(1)
    bad = _FakeGenerator()
    bad.generate = lambda **_: SourceProfileBatch.model_validate({"profiles": [{
        "url": URLS[0], "candidate_id": "wrong", "source_profile": _profile().model_dump(mode="json")}]})
    with pytest.raises(ValueError, match="candidate identity"):
        profile_module._generate_profiles(bad, state["candidate_sources"],
                                          profile_module._previews(state), task_name="identity")

    captured = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return json.dumps({"model": "jev-latest", "answers": {key: {"type": "noul", "noul": value}
            for key, value in CHECKS.items()}, "usage": {"input_tokens": 12, "output_tokens": 1}}).encode()
    def fake_urlopen(request, *, timeout):
        captured.append((request, timeout))
        return Response()
    monkeypatch.setattr("src.tools.structured_generation.jev_provider.urlopen", fake_urlopen)
    provider = JevDecisionProvider(api_key="test-key")
    assert provider.verify_profile(preview=SourcePreview.model_validate(_preview(URLS[0])),
                                   profile=_profile()) == CHECKS
    request, _ = captured[0]
    assert request.get_header("Authorization") == "Bearer test-key"
    assert json.loads(request.data)["model"] == settings.jev_model
    assert provider.metrics()["jev_input_tokens"] == 12


def test_jev_score_requires_typed_response(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): return None
        def read(self): return json.dumps({"model": "jev-latest", "usage": {"input_tokens": 2, "output_tokens": 1}, "answers": {
            "topic_purpose_relevance": {"type": "score", "score": 3, "confidence": .9,
                                        "legend": {"0": "Unrelated", "4": "Direct"},
                                        "probabilities": {"3": 1.0}}}}).encode()
    monkeypatch.setattr("src.tools.structured_generation.jev_provider.urlopen",
                        lambda request, timeout: Response())
    provider = JevDecisionProvider(api_key="test-key")
    assert provider.score_relevance(preview=SourcePreview.model_validate(_preview(URLS[0])),
                                    topic="Topic", purpose="Purpose") == (.75, .9)


def test_jev_routing_is_opt_in_and_legacy_graph_route_remains(monkeypatch):
    jev_settings = replace(settings, source_evaluator_provider="jev", data_source_provider="crawl4ai")
    monkeypatch.setattr(phase2_pipeline, "settings", jev_settings)
    monkeypatch.setattr("src.tools.structured_generation.source_evaluation_provider.settings", jev_settings)
    assert phase2_pipeline._after_preview({"status": "sources_previewed"}) == "source_profile_generation"
    assert isinstance(get_source_evaluation_provider(), JevDecisionProvider)
    monkeypatch.setattr(phase2_pipeline, "settings", replace(jev_settings, source_evaluator_provider="groq"))
    assert phase2_pipeline._after_preview({"status": "sources_previewed"}) == "source_evaluator"
    assert phase2_pipeline._after_preview({"status": "failed"}) == phase2_pipeline.END


def test_jev_evaluator_node_persists_profile_and_policy_decisions(monkeypatch):
    state = _state(1)
    state["source_profile_verifications"] = [{"url": URLS[0], "candidate_id": "cand_1",
        "source_profile": _profile().model_dump(mode="json"), "status": "accepted",
        "provider": "ollama", "checks": CHECKS}]
    monkeypatch.setattr(evaluator_module, "settings", replace(
        settings, source_evaluator_provider="jev", data_source_provider="crawl4ai"))
    monkeypatch.setattr(evaluator_module, "get_source_evaluation_provider", lambda: _FakeJev())
    result = evaluator_module.source_evaluator_node(state)
    assert result["status"] == "sources_evaluated", result.get("errors")
    assert result["source_evaluations"][0]["candidate_id"] == "cand_1"
    assert result["source_evaluations"][0]["profile_provider"] == "ollama"
    assert result["source_evaluations"][0]["profile_verification_checks"] == CHECKS
    assert result["source_evaluations"][0]["topic_purpose_confidence"] == .95
    assert result["source_evaluation_metrics"]["scored_candidates"] == 1
    assert result["source_evaluation_metrics"]["jev_relevance_score_calls"] == 1
    assert result["selected_sources"][0]["url"] == URLS[0]


def test_evaluator_rejects_stale_accepted_profile_checks(monkeypatch):
    state = _state(1)
    state["source_profile_verifications"] = [{"url": URLS[0], "candidate_id": "cand_1",
        "source_profile": _profile().model_dump(mode="json"), "status": "accepted",
        "provider": "ollama", "checks": {**CHECKS, "scores_supported": .5}}]
    monkeypatch.setattr(evaluator_module, "get_source_evaluation_provider", lambda: _FakeJev())
    with pytest.raises(ValueError, match="insufficient Jev evidence support"):
        evaluator_module._jev_evaluation(state, evaluator_module.build_source_evaluator_input(state))


def test_duplicate_profile_proposals_fail_identity_check():
    state = _state(1)
    proposal = {"url": URLS[0], "candidate_id": "cand_1",
                "source_profile": _profile().model_dump(mode="json")}
    state["source_profile_proposals"] = [proposal, proposal]
    result = profile_module.source_profile_verification_node(state)
    assert result["status"] == "failed"
    assert "duplicate URL" in result["errors"][-1]["error"]
