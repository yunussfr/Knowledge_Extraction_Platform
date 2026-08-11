from typing import Dict, Any, List


def _build_co_occurrence_relations(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Creates RELATED_TO relations for every entity pair in the same document."""
    relations = []
    for i, src in enumerate(entities):
        for tgt in entities[i + 1:]:
            relations.append({
                "source_entity": src["name"],
                "target_entity": tgt["name"],
                "relation_type": "RELATED_TO",
                "attributes": {"method": "co_occurrence"}
            })
    return relations


def _apply_relation_config(
    relations: List[Dict[str, Any]],
    config: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Applies config-driven relation type overrides based on entity type pairs."""
    relation_rules: List[Dict] = config.get("relation_rules", [])
    for rel in relations:
        for rule in relation_rules:
            if (
                rule.get("source_type") == rel.get("source_entity")
                or rule.get("target_type") == rel.get("target_entity")
            ):
                rel["relation_type"] = rule.get("relation_type", rel["relation_type"])
    return relations


def relation_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Phase 2: Extracts relations between entities using co-occurrence.
    Config-driven relation type overrides. No hardcoded domain logic.
    """
    try:
        enriched_data: List[Dict[str, Any]] = state.get("enriched_data", [])
        config: Dict[str, Any] = state.get("config", {})

        print("Extracting relations...")
        result = []
        for item in enriched_data:
            updated = item.copy()
            entities = item.get("entities", [])
            relations = _build_co_occurrence_relations(entities)
            relations = _apply_relation_config(relations, config)
            updated["relations"] = relations
            result.append(updated)

        return {"enriched_data": result, "status": "validating"}
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "relation_extraction", "error": str(e)}],
            "status": "failed"
        }
