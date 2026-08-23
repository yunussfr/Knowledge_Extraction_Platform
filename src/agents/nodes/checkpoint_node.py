"""Graph node factory for stage-level resumable checkpoints."""

from typing import Any, Callable, Dict

from src.core.checkpoint import write_checkpoint


def checkpoint_node(stage: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    def node(state: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return write_checkpoint(state, stage)
        except Exception as error:
            return {
                "errors": state.get("errors", []) + [{
                    "node": "checkpoint",
                    "stage": stage,
                    "error": str(error),
                }],
                "status": "failed",
                "pipeline_status": "failed",
            }
    return node
