from typing import Dict, Any, List


def _compute_completeness_score(item: Dict[str, Any]) -> float:
    """Scores completeness based on presence of key fields (0.0-1.0)."""
    required_fields = ["cleaned_content", "entities", "relations", "metadata"]
    present = sum(1 for f in required_fields if item.get(f))
    return round(present / len(required_fields), 2)


def _compute_content_score(content: str, min_words: int = 10) -> float:
    """Scores content quality based on word count threshold."""
    word_count = len(content.split())
    if word_count == 0:
        return 0.0
    return min(round(word_count / (min_words * 10), 2), 1.0)


def _build_quality_report(item: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Aggregates quality metrics for a single item."""
    content = item.get("cleaned_content", "")
    min_words = config.get("quality", {}).get("min_words", 10)
    completeness = _compute_completeness_score(item)
    content_score = _compute_content_score(content, min_words)
    overall = round((completeness + content_score) / 2, 2)
    minimum_confidence = config.get("quality", {}).get("minimum_confidence", 0.0)
    confidence = float(item.get("metadata", {}).get("confidence_score", 0.0))
    return {
        "completeness_score": completeness,
        "content_score": content_score,
        "overall_quality_score": overall,
        "confidence": confidence,
        "confidence_passed": confidence >= minimum_confidence,
        "passed": overall >= config.get("quality", {}).get("min_quality_score", 0.4)
        and confidence >= minimum_confidence,
    }


def quality_analysis_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Scores document quality using completeness and content metrics.
    Writes quality_report field to each enriched item. Config-driven thresholds.
    """
    try:
        enriched_data: List[Dict[str, Any]] = state.get("enriched_data", [])
        config: Dict[str, Any] = state.get("config", {})

        print("Analyzing document quality...")
        result = []
        for item in enriched_data:
            updated = item.copy()
            updated["quality_report"] = _build_quality_report(item, config)
            result.append(updated)

        return {"enriched_data": result, "status": "quality_check", "pipeline_status": "quality_check"}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "quality_analysis", "error": str(e)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
