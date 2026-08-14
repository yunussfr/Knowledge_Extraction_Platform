"""Phase 9 request-specific source characterization and policy tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from src.agents.nodes.source_evaluator_node import (
    build_source_evaluator_input,
    source_evaluator_node,
)
from src.agents.nodes.source_selector_node import source_selector_node
from src.core.settings import settings
from src.core.source_policy_evaluator import evaluate_source_for_policy
from src.core.source_registry import CandidateRegistry
from src.schemas.models import (
    DiscoveryOrigin,
    EvaluatedSource,
    SourceEvaluationResult,
    SourceImportance,
    SourcePolicy,
    SourceProfile,
)
from src.tools.web.models import SourcePreview


def _preview(url: str, *, success: bool = True) -> SourcePreview:
    return SourcePreview(
        url=url,
        title="Evidence",
        domain=url.split("/")[2],
        relevant_text="Detailed bounded source evidence." if success else "",
        approximate_word_count=500 if success else 0,
        preview_word_count=5 if success else 0,
        fetch_success=success,
        error=None if success else "fixture fetch failed",
    )


def _deep_independent() -> SourceProfile:
    return SourceProfile(
        source_type="independent_technical",
        content_characteristics=[
            "technical_explanation",
            "implementation_details",
            "benchmark",
        ],
        content_depth="deep",
        authority_signals=["reproducible_code", "reported_limitations"],
        authority_score=0.40,
        information_density_score=0.92,
        technical_depth_score=0.96,
        recency_score=0.70,
        extractability_score=0.86,
    )


def _shallow_official() -> SourceProfile:
    return SourceProfile(
        source_type="government",
        content_characteristics=["shallow_summary", "primary_facts"],
        content_depth="shallow",
        authority_signals=["official_publisher"],
        authority_score=0.96,
        information_density_score=0.28,
        technical_depth_score=0.18,
        recency_score=0.70,
        extractability_score=0.72,
    )


def _evaluate(
    profile: SourceProfile,
    policy: SourcePolicy,
    *,
    url: str = "https://independent.example/source",
    relevance: float = 0.92,
    preview_success: bool = True,
    preferred_domains: list[str] | None = None,
    allowed_domains: list[str] | None = None,
    blocked_domains: list[str] | None = None,
):
    return evaluate_source_for_policy(
        url=url,
        profile=profile,
        topic_relevance_score=relevance,
        preview=_preview(url, success=preview_success),
        policy=policy,
        preferred_domains=preferred_domains,
        allowed_domains=allowed_domains,
        blocked_domains=blocked_domains,
    )


def test_profile_labels_are_extensible_normalized_and_score_bounded():
    profile = SourceProfile(
        source_type="Community Research Note",
        content_characteristics=["Implementation Details", "implementation-details"],
        authority_signals=["Open Code"],
        authority_score=0.7,
        information_density_score=0.8,
        technical_depth_score=0.9,
        extractability_score=0.6,
    )

    assert profile.source_type == "community_research_note"
    assert profile.content_characteristics == ["implementation_details"]
    assert profile.authority_signals == ["open_code"]
    with pytest.raises(ValidationError):
        SourceProfile(technical_depth_score=1.1)
    with pytest.raises(ValidationError):
        EvaluatedSource(
            url="https://example.com",
            source_profile=profile,
            topic_relevance_score=-0.1,
        )


def test_shallow_official_loses_to_deep_independent_for_technical_policy():
    policy = SourcePolicy(
        desired_content=["technical_explanation", "implementation_details"],
        importance=SourceImportance(
            authority="low",
            technical_depth="high",
            information_density="high",
            recency="low",
            extractability="medium",
        ),
    )

    official = _evaluate(
        _shallow_official(),
        policy,
        url="https://gov.example/overview",
    )
    independent = _evaluate(_deep_independent(), policy)

    assert independent.hard_policy_rejected is False
    assert official.hard_policy_rejected is False
    assert independent.final_score > official.final_score
    assert independent.policy_alignment_score > official.policy_alignment_score
    assert independent.decision == "select"


def test_independent_source_is_not_penalized_under_neutral_policy():
    result = _evaluate(_deep_independent(), SourcePolicy())

    assert result.hard_policy_rejected is False
    assert result.decision == "select"
    assert not any("independent" in reason.casefold() for reason in result.reasons)


def test_allowed_source_types_apply_only_when_nonempty():
    neutral = _evaluate(_deep_independent(), SourcePolicy(allowed_source_types=None))
    empty = _evaluate(_deep_independent(), SourcePolicy(allowed_source_types=[]))
    restricted = _evaluate(
        _deep_independent(),
        SourcePolicy(allowed_source_types=["government", "university"]),
    )

    assert neutral.hard_policy_rejected is False
    assert empty.hard_policy_rejected is False
    assert restricted.hard_policy_rejected is True
    assert restricted.decision == "reject"


def test_blocked_source_types_apply_only_when_nonempty():
    neutral = _evaluate(_deep_independent(), SourcePolicy(blocked_source_types=None))
    empty = _evaluate(_deep_independent(), SourcePolicy(blocked_source_types=[]))
    blocked = _evaluate(
        _deep_independent(),
        SourcePolicy(blocked_source_types=["Independent Technical"]),
    )

    assert neutral.hard_policy_rejected is False
    assert empty.hard_policy_rejected is False
    assert blocked.hard_policy_rejected is True
    assert "explicitly blocked" in " ".join(blocked.reasons)


def test_preferred_source_type_is_soft_and_does_not_reject_alternative():
    policy = SourcePolicy(preferred_source_types=["government"])
    independent = _evaluate(_deep_independent(), policy)
    official = _evaluate(
        _shallow_official(),
        policy,
        url="https://gov.example/overview",
    )

    assert independent.hard_policy_rejected is False
    assert independent.decision == "select"
    assert official.hard_policy_rejected is False
    assert any("soft preferred source type" in reason for reason in official.reasons)


def test_domain_hard_rules_and_soft_preference_are_distinct():
    profile = _deep_independent()
    preferred_only = _evaluate(
        profile,
        SourcePolicy(),
        preferred_domains=["other.example"],
    )
    outside_allowlist = _evaluate(
        profile,
        SourcePolicy(),
        allowed_domains=["allowed.example"],
    )
    blocked = _evaluate(
        profile,
        SourcePolicy(),
        blocked_domains=["independent.example"],
    )

    assert preferred_only.hard_policy_rejected is False
    assert outside_allowlist.hard_policy_rejected is True
    assert blocked.hard_policy_rejected is True


def test_minimum_content_depth_is_hard_only_when_explicit():
    shallow = _shallow_official()
    unrestricted = _evaluate(
        shallow,
        SourcePolicy(),
        url="https://gov.example/overview",
    )
    deep_required = _evaluate(
        shallow,
        SourcePolicy(minimum_content_depth="deep"),
        url="https://gov.example/overview",
    )

    assert unrestricted.hard_policy_rejected is False
    assert deep_required.hard_policy_rejected is True
    assert "below explicit minimum" in " ".join(deep_required.reasons)


def test_same_source_scores_differently_under_different_policies():
    profile = _deep_independent()
    technical_policy = SourcePolicy(
        desired_content=["technical_explanation", "implementation_details"],
        importance=SourceImportance(technical_depth="high", information_density="high"),
    )
    authority_policy = SourcePolicy(
        importance=SourceImportance(authority="high", technical_depth="low"),
    )

    technical = _evaluate(profile, technical_policy)
    authority = _evaluate(profile, authority_policy)

    assert technical.source_profile == authority.source_profile
    assert technical.policy_alignment_score != authority.policy_alignment_score
    assert technical.final_score != authority.final_score


def test_avoided_content_lowers_score_without_becoming_hard_rule():
    profile = SourceProfile(
        **{
            **_deep_independent().model_dump(),
            "content_characteristics": ["technical_explanation", "marketing"],
        }
    )
    neutral = _evaluate(profile, SourcePolicy())
    avoided = _evaluate(profile, SourcePolicy(avoided_content=["marketing"]))

    assert avoided.hard_policy_rejected is False
    assert avoided.policy_alignment_score < neutral.policy_alignment_score


def test_preview_failure_is_visible_but_not_an_invented_hard_policy_violation():
    result = _evaluate(
        _deep_independent(),
        SourcePolicy(),
        preview_success=False,
    )

    assert result.preview_success is False
    assert result.decision == "reject"
    assert result.hard_policy_rejected is False
    assert "fixture fetch failed" in " ".join(result.reasons)


def test_evaluator_input_preserves_absent_hard_controls_and_full_request_context():
    state = {
        "dataset_topic": "Attention kernels",
        "dataset_purpose": "Technical RAG",
        "source_policy": SourcePolicy(
            desired_content=["implementation_details"]
        ).model_dump(mode="json"),
        "research_plan": {"search_queries": ["attention kernel"]},
        "config": {
            "research": {"constraints": "Prefer reproducible evidence."},
            "sources": {
                "preferred_domains": ["preferred.example"],
                "allowed_domains": None,
                "blocked_domains": None,
            },
        },
        "candidate_sources": [{"url": "https://example.com/source"}],
        "source_previews": [_preview("https://example.com/source").model_dump()],
    }

    evaluator_input = build_source_evaluator_input(state)

    assert evaluator_input.dataset_purpose == "Technical RAG"
    assert evaluator_input.source_policy.desired_content == ["implementation_details"]
    assert evaluator_input.preferred_domains == ["preferred.example"]
    assert evaluator_input.allowed_domains is None
    assert evaluator_input.blocked_domains is None
    assert evaluator_input.research_constraints == "Prefer reproducible evidence."


def test_live_boundary_recomputes_policy_and_rejects_model_hard_rule_bypass(monkeypatch):
    url = "https://independent.example/source"
    registry = CandidateRegistry()
    registry.add(
        url,
        origin=DiscoveryOrigin(method="search", query="attention implementation"),
        source_provider="fixture",
    )

    def fake_complete_json(self, system_prompt, user_prompt, output_model):
        payload = json.loads(user_prompt)
        assert payload["evaluator_input"]["source_policy"]["allowed_source_types"] == [
            "government"
        ]
        return SourceEvaluationResult(evaluated_sources=[EvaluatedSource(
            url=url,
            source_profile=_deep_independent(),
            topic_relevance_score=0.99,
            policy_alignment_score=1.0,
            final_score=1.0,
            hard_policy_rejected=False,
            decision="select",
            reasons=["Model proposed selection."],
        )])

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_evaluator_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = source_evaluator_node({
            "dataset_topic": "Attention",
            "dataset_purpose": "Technical RAG",
            "source_policy": SourcePolicy(
                allowed_source_types=["government"]
            ).model_dump(mode="json"),
            "research_plan": {},
            "config": {
                "research": {"max_sources": 5},
                "sources": {
                    "source_policy": {"allowed_source_types": ["government"]},
                },
            },
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [_preview(url).model_dump(mode="json")],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "sources_evaluated"
    evaluation = EvaluatedSource.model_validate(result["source_evaluations"][0])
    assert evaluation.hard_policy_rejected is True
    assert evaluation.decision == "reject"

    selection = source_selector_node({
        **result,
        "config": {
            "research": {"max_sources": 5},
            "sources": {
                "source_policy": {"allowed_source_types": ["government"]},
            },
        },
        "source_policy": SourcePolicy(
            allowed_source_types=["government"]
        ).model_dump(mode="json"),
        "errors": [],
    })
    assert selection["status"] == "failed"
    assert "no eligible source" in selection["errors"][-1]["error"]


def test_live_boundary_rejects_omitted_or_invented_candidate_urls(monkeypatch):
    urls = ["https://example.com/one", "https://example.com/two"]
    registry = CandidateRegistry()
    for index, url in enumerate(urls):
        registry.add(url, origin=DiscoveryOrigin(method="search", query=f"q{index}"))

    def fake_complete_json(self, system_prompt, user_prompt, output_model):
        return SourceEvaluationResult(evaluated_sources=[EvaluatedSource(
            url="https://invented.example/source",
            source_profile=_deep_independent(),
            topic_relevance_score=0.9,
        )])

    original_provider = settings.data_source_provider
    object.__setattr__(settings, "data_source_provider", "firecrawl")
    monkeypatch.setattr(
        "src.agents.nodes.source_evaluator_node.GroqClient.complete_json",
        fake_complete_json,
    )
    try:
        result = source_evaluator_node({
            "dataset_topic": "Attention",
            "dataset_purpose": "RAG",
            "source_policy": SourcePolicy().model_dump(mode="json"),
            "config": {"research": {"max_sources": 5}, "sources": {}},
            "candidate_sources": registry.as_pipeline_candidates(),
            "source_registry": registry.as_serialized(),
            "source_previews": [_preview(url).model_dump(mode="json") for url in urls],
            "errors": [],
        })
    finally:
        object.__setattr__(settings, "data_source_provider", original_provider)

    assert result["status"] == "failed"
    assert "unknown URL" in result["errors"][-1]["error"]
