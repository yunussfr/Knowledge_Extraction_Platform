import re
import unicodedata
from typing import Dict, Any, List


def _normalize_whitespace(text: str) -> str:
    """Collapses multiple spaces/newlines into single spaces."""
    return re.sub(r"\s+", " ", text).strip()


def _normalize_unicode(text: str) -> str:
    """Applies NFC unicode normalization to ensure consistent character forms."""
    return unicodedata.normalize("NFC", text)


def _apply_custom_replacements(text: str, replacements: Dict[str, str]) -> str:
    """Applies config-driven text replacements (e.g., abbreviation expansions)."""
    for pattern, replacement in replacements.items():
        text = text.replace(pattern, replacement)
    return text


def _normalize_content(text: str, config: Dict[str, Any]) -> str:
    """Applies the full normalization pipeline to a text string."""
    replacements: Dict[str, str] = config.get("normalization", {}).get("replacements", {})
    text = _normalize_unicode(text)
    text = _normalize_whitespace(text)
    text = _apply_custom_replacements(text, replacements)
    return text


def normalization_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Normalizes document content (unicode, whitespace, custom replacements).
    Writes normalized_content field. All rules come from config — zero domain hardcoding.
    """
    try:
        enriched_data: List[Dict[str, Any]] = state.get("enriched_data", [])
        config: Dict[str, Any] = state.get("config", {})

        print("Normalizing documents...")
        result = []
        for item in enriched_data:
            updated = item.copy()
            raw = item.get("cleaned_content", "")
            updated["normalized_content"] = _normalize_content(raw, config)
            result.append(updated)

        return {"enriched_data": result, "status": "validating"}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "normalization", "error": str(e)}],
            "status": "failed"
        }
