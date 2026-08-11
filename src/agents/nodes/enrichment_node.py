from typing import Dict, Any
from src.state.state import AgentState

def enrichment_node(state: AgentState) -> Dict[str, Any]:
    try:
        # This node handles Metadata Builder, Entity Extractor, Relation Extractor
        processed_data = state.get("processed_data", [])
        enriched_data = state.get("enriched_data", [])
        
        print("Enriching data (Extracting Entities/Relations)...")
        for item in processed_data:
            enriched_item = {
                "source": item.get("source"),
                "cleaned_content": item.get("cleaned_content"),
                "entities": [
                    {"name": "MockEntity", "type": "MockType", "attributes": {}}
                ],
                "relations": [
                    {"source_entity": "MockEntity", "target_entity": "OtherEntity", "relation_type": "MOCK_REL"}
                ],
                "metadata": {
                    "source_url": item.get("source"),
                    "extracted_at": "2026-07-31"
                }
            }
            enriched_data.append(enriched_item)
            
        return {
            "enriched_data": enriched_data,
            "status": "validating"
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "enrichment", "error": str(e)}],
            "status": "failed"
        }
