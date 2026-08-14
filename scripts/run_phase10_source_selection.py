"""Benchmark Phase 10 selection on the frozen Phase 1 source candidate set."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import Any
from urllib.parse import urlparse

from scripts.run_phase9_source_evaluation import _profile
from src.agents.nodes.source_selector_node import select_sources
from src.core.source_policy_evaluator import evaluate_source_for_policy
from src.evaluation.metrics import load_json
from src.schemas.models import EvaluatedSource, SourcePolicy
from src.tools.web.models import SourcePreview


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = PROJECT_ROOT / "tests" / "evaluation" / "fixtures" / "source_evaluation_gold.json"
SELECTION_LIMIT = 5
DUPLICATE_OF = {
    "duplicate_independent_page": "independent_deep_relevant",
    "academic_duplicate": "academic_deep_relevant",
}


def _evaluate_candidates(
    candidates: list[dict[str, Any]],
    policy: SourcePolicy,
) -> list[EvaluatedSource]:
    url_by_id = {candidate["id"]: candidate["url"] for candidate in candidates}
    evaluated: list[EvaluatedSource] = []
    for candidate in candidates:
        preview = SourcePreview(
            url=candidate["url"],
            title=candidate["id"],
            domain=urlparse(candidate["url"]).hostname or "",
            relevant_text=candidate["preview"],
            approximate_word_count=len(candidate["preview"].split()),
            preview_word_count=len(candidate["preview"].split()),
            fetch_success=True,
        )
        result = evaluate_source_for_policy(
            url=candidate["url"],
            profile=_profile(candidate),
            topic_relevance_score=0.10 if "irrelevant" in candidate["cases"] else 0.90,
            preview=preview,
            policy=policy,
        )
        duplicate_id = DUPLICATE_OF.get(candidate["id"])
        if duplicate_id:
            result = result.model_copy(update={"duplicate_of": url_by_id[duplicate_id]})
        evaluated.append(result)
    return evaluated


def _metrics(
    selected_urls: list[str],
    candidates: list[dict[str, Any]],
    policy_id: str,
) -> dict[str, Any]:
    candidate_by_url = {candidate["url"]: candidate for candidate in candidates}
    selected = [candidate_by_url[url] for url in selected_urls]
    domains = [(urlparse(item["url"]).hostname or "").lower() for item in selected]
    types = [item["source_type"] for item in selected]
    duplicate_count = sum(item["id"] in DUPLICATE_OF for item in selected)
    useful = sum(item["expected"][policy_id]["decision"] == "select" for item in selected)
    hard_violations = sum(
        item["expected"][policy_id]["hard_policy_rejected"] for item in selected
    )
    max_domain_count = max((domains.count(domain) for domain in set(domains)), default=0)
    return {
        "selected_count": len(selected),
        "precision": round(useful / len(selected), 6) if selected else 0.0,
        "hard_policy_violation_rate": (
            round(hard_violations / len(selected), 6) if selected else 0.0
        ),
        "unique_domain_count": len(set(domains)),
        "unique_source_type_count": len(set(types)),
        "max_domain_share": (
            round(max_domain_count / len(selected), 6) if selected else 0.0
        ),
        "duplicate_selection_rate": (
            round(duplicate_count / len(selected), 6) if selected else 0.0
        ),
        "selected_candidate_ids": [item["id"] for item in selected],
    }


def run_evaluation() -> dict[str, Any]:
    gold = load_json(FIXTURE)
    before: dict[str, dict[str, Any]] = {}
    after: dict[str, dict[str, Any]] = {}
    for policy_id, raw_policy in gold["policies"].items():
        policy = SourcePolicy.model_validate(raw_policy)
        evaluations = _evaluate_candidates(gold["candidates"], policy)
        eligible = sorted(
            (
                item
                for item in evaluations
                if item.decision == "select"
                and not item.hard_policy_rejected
                and item.preview_success
            ),
            key=lambda item: (-item.final_score, evaluations.index(item)),
        )
        before[policy_id] = _metrics(
            [item.url for item in eligible[:SELECTION_LIMIT]],
            gold["candidates"],
            policy_id,
        )
        selections, _ = select_sources(
            evaluations,
            policy=policy,
            max_sources=SELECTION_LIMIT,
        )
        after[policy_id] = _metrics(
            [item.url for item in selections],
            gold["candidates"],
            policy_id,
        )

    aggregate_fields = [
        "precision",
        "hard_policy_violation_rate",
        "unique_domain_count",
        "unique_source_type_count",
        "max_domain_share",
        "duplicate_selection_rate",
    ]

    def aggregate(values: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {
            field: round(fmean(item[field] for item in values.values()), 6)
            for field in aggregate_fields
        }

    before_aggregate = aggregate(before)
    after_aggregate = aggregate(after)
    return {
        "benchmark_version": gold["benchmark_version"],
        "implementation": "phase10_policy_aware_diversity_selector",
        "selection_limit": SELECTION_LIMIT,
        "before": before_aggregate,
        "after": after_aggregate,
        "delta": {
            field: round(after_aggregate[field] - before_aggregate[field], 6)
            for field in aggregate_fields
        },
        "before_by_policy": before,
        "after_by_policy": after,
    }


def main() -> None:
    print(json.dumps(run_evaluation(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
