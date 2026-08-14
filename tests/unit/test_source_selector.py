"""Phase 10 deterministic, policy-aware source selection tests."""

from __future__ import annotations

from src.agents.nodes.source_selector_node import (
    _selection_metrics,
    select_sources,
    source_selector_node,
)
from src.core.source_registry import CandidateRegistry
from src.schemas.models import (
    DiscoveryOrigin,
    EvaluatedSource,
    SourceImportance,
    SourcePolicy,
    SourceProfile,
)


def _evaluated(
    url: str,
    *,
    final_score: float,
    source_type: str = "independent_technical",
    density: float | None = None,
    technical_depth: float | None = None,
    extractability: float | None = None,
    decision: str = "select",
    hard_rejected: bool = False,
    preview_success: bool = True,
    duplicate_of: str | None = None,
) -> EvaluatedSource:
    return EvaluatedSource(
        url=url,
        source_profile=SourceProfile(
            source_type=source_type,
            content_depth="deep",
            information_density_score=density if density is not None else final_score,
            technical_depth_score=(
                technical_depth if technical_depth is not None else final_score
            ),
            extractability_score=(
                extractability if extractability is not None else final_score
            ),
        ),
        topic_relevance_score=final_score,
        policy_alignment_score=final_score,
        final_score=final_score,
        hard_policy_rejected=hard_rejected,
        decision=decision,
        reasons=["Fixture evaluation."],
        preview_success=preview_success,
        duplicate_of=duplicate_of,
    )


def test_one_domain_does_not_dominate_when_comparable_alternative_exists():
    evaluations = [
        _evaluated("https://dominant.example/a", final_score=0.90),
        _evaluated("https://dominant.example/b", final_score=0.88),
        _evaluated("https://dominant.example/c", final_score=0.86),
        _evaluated("https://alternative.example/a", final_score=0.84),
    ]

    selected, _ = select_sources(
        evaluations,
        policy=SourcePolicy(),
        max_sources=3,
    )

    assert [item.url for item in selected][:2] == [
        "https://dominant.example/a",
        "https://alternative.example/a",
    ]
    assert len({item.domain for item in selected}) == 2


def test_diversity_does_not_force_a_low_quality_source():
    evaluations = [
        _evaluated("https://strong.example/a", final_score=0.95),
        _evaluated("https://strong.example/b", final_score=0.90),
        _evaluated("https://weak.example/a", final_score=0.40),
    ]

    selected, _ = select_sources(
        evaluations,
        policy=SourcePolicy(),
        max_sources=2,
    )

    assert [item.url for item in selected] == [
        "https://strong.example/a",
        "https://strong.example/b",
    ]


def test_hard_rejected_and_preview_failed_sources_are_never_selected():
    evaluations = [
        _evaluated(
            "https://blocked.example/a",
            final_score=1.0,
            hard_rejected=True,
        ),
        _evaluated(
            "https://unavailable.example/a",
            final_score=0.99,
            preview_success=False,
        ),
        _evaluated("https://usable.example/a", final_score=0.70),
    ]

    selected, not_selected = select_sources(
        evaluations,
        policy=SourcePolicy(),
        max_sources=3,
    )

    assert [item.url for item in selected] == ["https://usable.example/a"]
    assert {item.url for item in not_selected} == {
        "https://blocked.example/a",
        "https://unavailable.example/a",
    }


def test_known_duplicate_source_is_not_selected_twice():
    original = _evaluated("https://original.example/a", final_score=0.90)
    duplicate = _evaluated(
        "https://mirror.example/a",
        final_score=0.95,
        duplicate_of=original.url,
    )

    selected, not_selected = select_sources(
        [original, duplicate],
        policy=SourcePolicy(),
        max_sources=2,
    )

    assert [item.url for item in selected] == [original.url]
    assert [item.url for item in not_selected] == [duplicate.url]


def test_preferred_type_is_not_a_mandatory_selection_filter():
    preferred_but_weaker = _evaluated(
        "https://official.example/a",
        final_score=0.65,
        source_type="government",
    )
    stronger_alternative = _evaluated(
        "https://technical.example/a",
        final_score=0.92,
        source_type="independent_technical",
    )

    selected, _ = select_sources(
        [preferred_but_weaker, stronger_alternative],
        policy=SourcePolicy(preferred_source_types=["government"]),
        max_sources=1,
    )

    assert selected[0].url == stronger_alternative.url


def test_technical_depth_importance_changes_request_specific_order():
    broad = _evaluated(
        "https://broad.example/a",
        final_score=0.80,
        density=0.90,
        technical_depth=0.20,
        extractability=0.90,
    )
    technical = _evaluated(
        "https://technical.example/a",
        final_score=0.78,
        density=0.70,
        technical_depth=1.0,
        extractability=0.70,
    )

    selected, _ = select_sources(
        [broad, technical],
        policy=SourcePolicy(
            importance=SourceImportance(technical_depth="high")
        ),
        max_sources=1,
    )

    assert selected[0].url == technical.url


def test_unique_domain_metrics_are_computed_from_actual_selections():
    evaluations = [
        _evaluated("https://one.example/a", final_score=0.90),
        _evaluated("https://one.example/b", final_score=0.85),
        _evaluated(
            "https://two.example/a",
            final_score=0.80,
            source_type="documentation",
        ),
    ]
    selections, _ = select_sources(
        evaluations,
        policy=SourcePolicy(),
        max_sources=3,
    )

    metrics = _selection_metrics(evaluations, selections)

    assert metrics["eligible_candidates"] == 3
    assert metrics["selected_sources"] == 3
    assert metrics["unique_selected_domains"] == 2
    assert metrics["selected_by_domain"] == {"one.example": 2, "two.example": 1}


def test_source_type_diversity_breaks_a_close_quality_choice():
    evaluations = [
        _evaluated("https://one.example/a", final_score=0.90, source_type="academic"),
        _evaluated("https://two.example/a", final_score=0.87, source_type="academic"),
        _evaluated("https://three.example/a", final_score=0.85, source_type="dataset"),
    ]

    selected, _ = select_sources(
        evaluations,
        policy=SourcePolicy(),
        max_sources=2,
    )

    assert [item.source_type for item in selected] == ["academic", "dataset"]


def test_selector_node_updates_final_registry_state_and_explains_rejections():
    evaluations = [
        _evaluated("https://one.example/a", final_score=0.90),
        _evaluated("https://two.example/a", final_score=0.80),
    ]
    registry = CandidateRegistry()
    for evaluation in evaluations:
        registry.add(
            evaluation.url,
            origin=DiscoveryOrigin(method="search", query="fixture"),
        )

    result = source_selector_node({
        "source_evaluations": [item.model_dump(mode="json") for item in evaluations],
        "source_registry": registry.as_serialized(),
        "candidate_sources": registry.as_pipeline_candidates(),
        "source_policy": SourcePolicy().model_dump(mode="json"),
        "config": {"research": {"max_sources": 1}, "sources": {}},
        "errors": [],
    })

    assert result["status"] == "sources_selected"
    assert len(result["selected_sources"]) == 1
    assert len(result["rejected_sources"]) == 1
    assert "source limit" in result["rejected_sources"][0]["reason"]
    selected_url = result["selected_sources"][0]["url"]
    rejected_url = result["rejected_sources"][0]["url"]
    assert result["source_registry"][selected_url]["selection_state"] == "selected"
    assert result["source_registry"][rejected_url]["selection_state"] == "rejected"


def test_selector_node_marks_identical_successful_previews_as_duplicates():
    evaluations = [
        _evaluated("https://one.example/a", final_score=0.90),
        _evaluated("https://mirror.example/a", final_score=0.80),
    ]
    registry = CandidateRegistry()
    for evaluation in evaluations:
        registry.add(
            evaluation.url,
            origin=DiscoveryOrigin(method="search", query="fixture"),
        )
    previews = [
        {
            "url": evaluation.url,
            "relevant_text": "The same bounded evidence.\n",
            "fetch_success": True,
        }
        for evaluation in evaluations
    ]

    result = source_selector_node({
        "source_evaluations": [item.model_dump(mode="json") for item in evaluations],
        "source_previews": previews,
        "source_registry": registry.as_serialized(),
        "candidate_sources": registry.as_pipeline_candidates(),
        "source_policy": SourcePolicy().model_dump(mode="json"),
        "config": {"research": {"max_sources": 2}, "sources": {}},
        "errors": [],
    })

    assert result["status"] == "sources_selected"
    assert [item["url"] for item in result["selected_sources"]] == [
        "https://one.example/a"
    ]
    assert result["source_selection_metrics"]["duplicate_candidates"] == 1
    assert "Exact preview duplicate" in result["rejected_sources"][0]["reason"]


def test_selector_node_fails_when_no_evaluated_source_is_eligible():
    rejected = _evaluated(
        "https://blocked.example/a",
        final_score=1.0,
        decision="reject",
        hard_rejected=True,
    )

    result = source_selector_node({
        "source_evaluations": [rejected.model_dump(mode="json")],
        "source_policy": SourcePolicy().model_dump(mode="json"),
        "config": {"research": {"max_sources": 2}, "sources": {}},
        "errors": [],
    })

    assert result["status"] == "failed"
    assert "no eligible source" in result["errors"][-1]["error"]
