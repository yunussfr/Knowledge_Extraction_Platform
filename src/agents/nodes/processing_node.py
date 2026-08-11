from typing import Dict, Any
from src.state.state import AgentState

def processing_node(state: AgentState) -> Dict[str, Any]:
    try:
        # This node is responsible for Parser, Cleaner, Filter Agents.
        raw_data = state.get("raw_data", [])
        processed_data = []
        errors = state.get("errors", [])
        
        print("Processing data...")
        for item in raw_data:
            # Simulated parsing and cleaning
            cleaned_content = item.get("content", "").replace("mock", "processed")
            processed_data.append({
                "source": item.get("source"),
                "title": item.get("title", ""),
                "cleaned_content": cleaned_content,
                "metadata": item.get("metadata", {}),
            })
            
        next_status = "processing" if state.get("dataset_topic") else "enriching"
        return {
            "processed_data": processed_data,
            "status": next_status,
            "pipeline_status": next_status,
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "processing", "error": str(e)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
