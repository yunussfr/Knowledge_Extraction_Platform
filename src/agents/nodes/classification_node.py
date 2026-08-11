from typing import Dict, Any, List


def _classify_document(content: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Determines document type and category from content and config."""
    categories = config.get("categories", ["general"])
    content_lower = content.lower()

    doc_type = "text"
    if "<html" in content_lower or "<body" in content_lower:
        doc_type = "html"
    elif content.strip().startswith("{") or content.strip().startswith("["):
        doc_type = "json"

    matched_category = "general"
    for category in categories:
        if category.lower() in content_lower:
            matched_category = category
            break

    return {"doc_type": doc_type, "category": matched_category}


def _apply_classification(item: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Applies classification result to a single processed item."""
    content = item.get("cleaned_content", "")
    classification = _classify_document(content, config)
    classified = item.copy()
    classified["doc_type"] = classification["doc_type"]
    classified["category"] = classification["category"]
    return classified


def classification_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Classifies documents by type and domain category.
    Reads processed_data, writes classification fields to each item.
    """
    try:
        processed_data: List[Dict[str, Any]] = state.get("processed_data", [])
        config: Dict[str, Any] = state.get("config", {})

        print("Classifying documents...")
        classified_data = [_apply_classification(item, config) for item in processed_data]

        return {
            "classified_data": classified_data,
            "status": "enriching"
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "classification", "error": str(e)}],
            "status": "failed"
        }
