import re
from typing import Dict, Any, List


def _extract_capitalized_entities(text: str) -> List[Dict[str, Any]]:
    """Extracts capitalized word sequences as candidate named entities."""
    pattern = r"\b([A-ZÜĞŞÇÖI][a-züğşçöi]+(?:\s+[A-ZÜĞŞÇÖI][a-züğşçöi]+)*)\b"
    matches = re.findall(pattern, text)
    seen = set()
    entities = []
    for match in matches:
        if match not in seen:
            seen.add(match)
            entities.append({
                "name": match,
                "type": "UNKNOWN",
                "attributes": {}
            })
    return entities


def _apply_entity_config_types(entities: List[Dict], config: Dict[str, Any]) -> List[Dict]:
    """Labels entities using type_mappings from domain config if provided."""
    type_mappings: Dict[str, str] = config.get("entity_type_mappings", {})
    for entity in entities:
        name_lower = entity["name"].lower()
        for keyword, etype in type_mappings.items():
            if keyword.lower() in name_lower:
                entity["type"] = etype
                break
    return entities


def entity_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Extracts named entities from enriched document content.
    Uses regex heuristics + config-driven type mapping (no hardcoded domain logic).
    """
    try:
        enriched_data: List[Dict[str, Any]] = state.get("enriched_data", [])
        config: Dict[str, Any] = state.get("config", {})

        print("Extracting entities...")
        result = []
        for item in enriched_data:
            updated = item.copy()
            content = item.get("cleaned_content", "")
            entities = _extract_capitalized_entities(content)
            entities = _apply_entity_config_types(entities, config)
            updated["entities"] = entities
            result.append(updated)

        return {"enriched_data": result, "status": "validating"}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "entity_extraction", "error": str(e)}],
            "status": "failed"
        }
