from langgraph.graph import StateGraph, END
from src.state.state import AgentState
from src.agents.nodes.acquisition_node import acquisition_node
from src.agents.nodes.processing_node import processing_node
from src.agents.nodes.enrichment_node import enrichment_node
from src.agents.nodes.validation_node import validation_node
from src.agents.nodes.export_node import export_node

def should_continue(state: AgentState):
    if state.get("status") == "failed":
        return END
    status = state.get("status")
    if status == "processing":
        return "processing"
    elif status == "enriching":
        return "enrichment"
    elif status == "validating":
        return "validation"
    elif status == "exporting":
        return "export"
    elif status == "completed":
        return END
    return END

def build_pipeline():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("acquisition", acquisition_node)
    workflow.add_node("processing", processing_node)
    workflow.add_node("enrichment", enrichment_node)
    workflow.add_node("validation", validation_node)
    workflow.add_node("export", export_node)
    
    # Add edges
    workflow.set_entry_point("acquisition")
    
    workflow.add_conditional_edges(
        "acquisition",
        should_continue,
        {
            "processing": "processing",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "processing",
        should_continue,
        {
            "enrichment": "enrichment",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "enrichment",
        should_continue,
        {
            "validation": "validation",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "validation",
        should_continue,
        {
            "export": "export",
            END: END
        }
    )
    
    workflow.add_edge("export", END)
    
    return workflow.compile()
