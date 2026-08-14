"""Deterministic metrics for the frozen source and extraction benchmarks."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean
from typing import Any


def load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def evaluate_sources(gold: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    """Score one fixed candidate ranking under every benchmark SourcePolicy."""
    candidates = gold["candidates"]
    policy_ids = list(gold["policies"])
    ranked_ids = predictions["source_predictions"]["ranked_candidate_ids"]
    selection_limit = int(predictions["source_predictions"]["selection_limit"])
    expected_by_id = {candidate["id"]: candidate["expected"] for candidate in candidates}
    candidate_ids = set(expected_by_id)
    if len(ranked_ids) != len(set(ranked_ids)) or set(ranked_ids) != candidate_ids:
        raise ValueError("Source prediction ranking must contain every candidate exactly once.")

    precision_at_5: dict[str, float] = {}
    precision_at_10: dict[str, float] = {}
    correct_decisions = 0
    total_decisions = 0
    selected_count = 0
    hard_violations = 0

    selected_ids = set(ranked_ids[:selection_limit])
    for policy_id in policy_ids:
        for k, destination in ((5, precision_at_5), (10, precision_at_10)):
            top_ids = ranked_ids[:k]
            useful = sum(
                expected_by_id[candidate_id][policy_id]["decision"] == "select"
                for candidate_id in top_ids
            )
            destination[policy_id] = _ratio(useful, len(top_ids))

        for candidate_id in ranked_ids:
            expected = expected_by_id[candidate_id][policy_id]
            predicted_decision = "select" if candidate_id in selected_ids else "reject"
            correct_decisions += predicted_decision == expected["decision"]
            total_decisions += 1
            if predicted_decision == "select":
                selected_count += 1
                hard_violations += bool(expected["hard_policy_rejected"])

    changed_outcomes = sum(
        len({candidate["expected"][policy_id]["decision"] for policy_id in policy_ids}) > 1
        for candidate in candidates
    )
    return {
        "candidate_count": len(candidates),
        "policy_count": len(policy_ids),
        "source_precision_at_5": round(fmean(precision_at_5.values()), 6),
        "source_precision_at_10": round(fmean(precision_at_10.values()), 6),
        "precision_at_5_by_policy": precision_at_5,
        "precision_at_10_by_policy": precision_at_10,
        "policy_alignment_accuracy": _ratio(correct_decisions, total_decisions),
        "hard_policy_violation_rate": _ratio(hard_violations, selected_count),
        "same_source_multi_policy_outcome_count": changed_outcomes,
    }


def evaluate_policy_source_predictions(
    gold: dict[str, Any],
    predictions_by_policy: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Measure request-specific rankings/decisions for every frozen policy."""
    candidates = gold["candidates"]
    candidate_ids = {candidate["id"] for candidate in candidates}
    expected_by_id = {candidate["id"]: candidate["expected"] for candidate in candidates}
    policy_ids = list(gold["policies"])
    if set(predictions_by_policy) != set(policy_ids):
        raise ValueError("Predictions must contain every benchmark policy exactly once.")

    precision_at_5: dict[str, float] = {}
    precision_at_10: dict[str, float] = {}
    alignment_by_policy: dict[str, float] = {}
    hard_violation_by_policy: dict[str, float] = {}
    total_correct = 0
    total_decisions = 0
    total_selected = 0
    total_hard_violations = 0

    for policy_id in policy_ids:
        predictions = predictions_by_policy[policy_id]
        ids = [item["candidate_id"] for item in predictions]
        if len(ids) != len(set(ids)) or set(ids) != candidate_ids:
            raise ValueError(
                f"Policy {policy_id} predictions must contain every candidate exactly once."
            )
        ranked = sorted(
            predictions,
            key=lambda item: (-float(item["final_score"]), ids.index(item["candidate_id"])),
        )
        for k, destination in ((5, precision_at_5), (10, precision_at_10)):
            top = ranked[:k]
            useful = sum(
                expected_by_id[item["candidate_id"]][policy_id]["decision"] == "select"
                for item in top
            )
            destination[policy_id] = _ratio(useful, len(top))

        correct = 0
        selected = 0
        hard_violations = 0
        for item in predictions:
            expected = expected_by_id[item["candidate_id"]][policy_id]
            decision = item["decision"]
            if decision not in {"select", "reject"}:
                raise ValueError(f"Unsupported source decision: {decision}")
            correct += decision == expected["decision"]
            if decision == "select":
                selected += 1
                hard_violations += bool(expected["hard_policy_rejected"])
        alignment_by_policy[policy_id] = _ratio(correct, len(predictions))
        hard_violation_by_policy[policy_id] = _ratio(hard_violations, selected)
        total_correct += correct
        total_decisions += len(predictions)
        total_selected += selected
        total_hard_violations += hard_violations

    changed_outcomes = sum(
        len({candidate["expected"][policy_id]["decision"] for policy_id in policy_ids}) > 1
        for candidate in candidates
    )
    return {
        "candidate_count": len(candidates),
        "policy_count": len(policy_ids),
        "source_precision_at_5": round(fmean(precision_at_5.values()), 6),
        "source_precision_at_10": round(fmean(precision_at_10.values()), 6),
        "precision_at_5_by_policy": precision_at_5,
        "precision_at_10_by_policy": precision_at_10,
        "policy_alignment_accuracy": _ratio(total_correct, total_decisions),
        "policy_alignment_accuracy_by_policy": alignment_by_policy,
        "hard_policy_violation_rate": _ratio(total_hard_violations, total_selected),
        "hard_policy_violation_rate_by_policy": hard_violation_by_policy,
        "same_source_multi_policy_outcome_count": changed_outcomes,
    }


def _matches_type(value: Any, field_type: str) -> bool:
    checks = {
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "array": lambda item: isinstance(item, list),
        "object": lambda item: isinstance(item, dict),
    }
    return field_type in checks and checks[field_type](value)


def _schema_valid(data: dict[str, Any], schema_fields: dict[str, dict[str, Any]]) -> bool:
    if any(field_name not in schema_fields for field_name in data):
        return False
    for field_name, contract in schema_fields.items():
        value = data.get(field_name)
        if contract["required"] and value is None:
            return False
        if value is not None and not _matches_type(value, contract["type"]):
            return False
    return True


def _fingerprint(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def evaluate_extraction(gold: dict[str, Any], predictions: dict[str, Any]) -> dict[str, Any]:
    """Measure record, field, schema, evidence, and duplicate behavior."""
    schema = gold["schema"]
    identity_field = schema["identity_field"]
    schema_fields = schema["fields"]
    pages = {page["page_id"]: page for page in gold["pages"]}
    predicted_pages = {item["page_id"]: item["records"] for item in predictions["extraction_predictions"]}

    expected_record_count = sum(len(page["expected_records"]) for page in pages.values())
    expected_field_count = sum(
        len(record["data"])
        for page in pages.values()
        for record in page["expected_records"]
    )
    predicted_record_count = 0
    predicted_field_count = 0
    matched_record_count = 0
    correct_predicted_fields = 0
    recalled_field_keys: set[tuple[str, str, str]] = set()
    schema_valid_count = 0
    unsupported_field_count = 0
    duplicate_count = 0

    for page_id, page in pages.items():
        gold_by_identity = {
            record["data"][identity_field]: record for record in page["expected_records"]
        }
        matched_identities: set[str] = set()
        seen_fingerprints: set[str] = set()
        for predicted in predicted_pages.get(page_id, []):
            predicted_record_count += 1
            data = predicted.get("data", {})
            predicted_field_count += len(data)
            fingerprint = _fingerprint(data)
            if fingerprint in seen_fingerprints:
                duplicate_count += 1
            seen_fingerprints.add(fingerprint)

            if _schema_valid(data, schema_fields):
                schema_valid_count += 1

            identity = data.get(identity_field)
            expected_record = gold_by_identity.get(identity)
            if expected_record and identity not in matched_identities:
                matched_record_count += 1
                matched_identities.add(identity)

            for field_name, value in data.items():
                if expected_record and expected_record["data"].get(field_name) == value:
                    correct_predicted_fields += 1
                    recalled_field_keys.add((page_id, str(identity), field_name))

                evidence_values = predicted.get("field_evidence", {}).get(field_name, [])
                traceable = any(
                    (
                        isinstance(evidence, str)
                        and evidence
                        and evidence in page["content"]
                    )
                    or (
                        isinstance(evidence, dict)
                        and evidence.get("source_url") == page["source_url"]
                        and isinstance(evidence.get("evidence_text"), str)
                        and evidence["evidence_text"]
                        and evidence["evidence_text"] in page["content"]
                    )
                    for evidence in evidence_values
                )
                if not traceable:
                    unsupported_field_count += 1

    unknown_pages = set(predicted_pages) - set(pages)
    if unknown_pages:
        raise ValueError(f"Predictions reference unknown extraction pages: {sorted(unknown_pages)}")

    return {
        "page_count": len(pages),
        "expected_records": expected_record_count,
        "predicted_records": predicted_record_count,
        "record_precision": _ratio(matched_record_count, predicted_record_count),
        "record_recall": _ratio(matched_record_count, expected_record_count),
        "field_precision": _ratio(correct_predicted_fields, predicted_field_count),
        "field_recall": _ratio(len(recalled_field_keys), expected_field_count),
        "schema_valid_rate": _ratio(schema_valid_count, predicted_record_count),
        "unsupported_field_rate": _ratio(unsupported_field_count, predicted_field_count),
        "duplicate_rate": _ratio(duplicate_count, predicted_record_count),
    }
