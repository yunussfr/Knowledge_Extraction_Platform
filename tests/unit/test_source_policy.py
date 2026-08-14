"""Phase 2 acceptance tests for deterministic SourcePolicy semantics."""

from pathlib import Path

import pytest

from src.core.config_loader import load_request_config, normalize_request_config
from src.schemas.models import SourceConfiguration, SourcePolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _minimal_request(**sources):
    return {
        "dataset": {
            "name": "policy_test",
            "topic": "Policy semantics",
            "purpose": "Verify deterministic request parsing.",
        },
        "sources": sources,
    }


def test_neutral_policy_has_no_hidden_restrictions_or_preferences():
    policy = SourcePolicy()

    assert policy.preferred_source_types == []
    assert policy.allowed_source_types is None
    assert policy.blocked_source_types is None
    assert policy.desired_content == []
    assert policy.avoided_content == []
    assert policy.minimum_content_depth is None
    assert policy.has_source_type_allowlist is False
    assert policy.has_source_type_blocklist is False


def test_preferred_types_are_soft_and_do_not_create_hard_lists():
    policy = SourcePolicy.model_validate({"preferred_source_types": ["academic"]})

    assert policy.preferred_source_types == ["academic"]
    assert policy.allowed_source_types is None
    assert policy.blocked_source_types is None


def test_allowed_types_apply_only_when_supplied_and_nonempty():
    allowed = SourcePolicy.model_validate({"allowed_source_types": ["academic"]})
    empty = SourcePolicy.model_validate({"allowed_source_types": []})

    assert allowed.has_source_type_allowlist is True
    assert empty.allowed_source_types == []
    assert empty.has_source_type_allowlist is False


def test_blocked_types_apply_only_when_supplied_and_nonempty():
    blocked = SourcePolicy.model_validate({"blocked_source_types": ["social_media"]})
    empty = SourcePolicy.model_validate({"blocked_source_types": []})

    assert blocked.has_source_type_blocklist is True
    assert empty.blocked_source_types == []
    assert empty.has_source_type_blocklist is False


def test_desired_content_only_does_not_invent_source_type_rules():
    policy = SourcePolicy.model_validate({"desired_content": ["implementation_details"]})

    assert policy.desired_content == ["implementation_details"]
    assert policy.allowed_source_types is None
    assert policy.blocked_source_types is None


def test_avoided_content_only_does_not_invent_source_type_rules():
    policy = SourcePolicy.model_validate({"avoided_content": ["marketing"]})

    assert policy.avoided_content == ["marketing"]
    assert policy.allowed_source_types is None
    assert policy.blocked_source_types is None


def test_technical_depth_heavy_policy_preserves_request_weight():
    policy = SourcePolicy.model_validate({
        "importance": {"authority": "low", "technical_depth": "high"}
    })

    assert policy.importance.authority == "low"
    assert policy.importance.technical_depth == "high"
    assert policy.importance.information_density == "medium"


def test_minimum_depth_omitted_creates_no_hard_depth_requirement():
    policy = SourcePolicy.model_validate({"desired_content": ["technical_explanation"]})

    assert policy.minimum_content_depth is None


def test_allowed_and_blocked_source_type_conflict_is_rejected():
    with pytest.raises(ValueError, match="both allowed and blocked"):
        SourcePolicy.model_validate({
            "allowed_source_types": ["Academic"],
            "blocked_source_types": ["academic"],
        })


def test_all_optional_source_type_fields_omitted_survive_request_boundary():
    normalized = normalize_request_config(_minimal_request(source_policy={}))
    policy = normalized["sources"]["source_policy"]

    assert policy["preferred_source_types"] == []
    assert policy["allowed_source_types"] is None
    assert policy["blocked_source_types"] is None


def test_legacy_source_controls_are_migrated_out_of_research_deterministically():
    normalized = normalize_request_config({
        "dataset": {
            "name": "legacy",
            "topic": "Legacy request",
            "purpose": "Compatibility",
        },
        "research": {
            "reference_urls": ["https://seed.example/page"],
            "preferred_domains": ["preferred.example"],
            "max_queries": 3,
        },
    })

    assert normalized["sources"]["seed_urls"] == ["https://seed.example/page"]
    assert normalized["sources"]["preferred_domains"] == ["preferred.example"]
    assert "reference_urls" not in normalized["research"]
    assert "preferred_domains" not in normalized["research"]


def test_domain_controls_are_separate_and_conflicts_are_rejected():
    controls = SourceConfiguration.model_validate({
        "seed_urls": ["https://seed.example/page"],
        "preferred_domains": ["Preferred.Example"],
        "allowed_domains": ["allowed.example"],
        "blocked_domains": ["blocked.example"],
    })

    assert controls.seed_urls == ["https://seed.example/page"]
    assert controls.preferred_domains == ["preferred.example"]
    assert controls.allowed_domains == ["allowed.example"]
    assert controls.blocked_domains == ["blocked.example"]
    with pytest.raises(ValueError, match="both allowed and blocked"):
        SourceConfiguration.model_validate({
            "allowed_domains": ["same.example"],
            "blocked_domains": ["same.example"],
        })


def test_request_examples_parse_through_typed_contract_with_optional_fields_omitted():
    turkish = load_request_config(PROJECT_ROOT / "configs/domains/turkish_culture/request.yaml")
    space = load_request_config(PROJECT_ROOT / "configs/domains/space_science/request.yaml")

    assert turkish["sources"]["preferred_domains"] == ["kulturportali.gov.tr"]
    assert turkish["sources"]["allowed_domains"] is None
    assert turkish["sources"]["source_policy"]["allowed_source_types"] is None
    assert space["sources"]["source_policy"]["preferred_source_types"] == []
    assert space["sources"]["source_policy"]["allowed_source_types"] is None
    assert space["sources"]["source_policy"]["blocked_source_types"] is None
