# Legacy Surface Audit

This audit records ambiguous files without deleting them. Removal requires a
separate import, checkpoint, CLI, and documentation migration proof.

| Surface | Current disposition | Evidence |
|---|---|---|
| `src/agents/graphs/phase2_pipeline.py` | Canonical orchestrator | `run_domain_test.py` and graph tests import `build_phase2_pipeline`. |
| `src/graph/` | Compatibility/older graph surface | Current CLI does not import it; retained until a dedicated migration proves no external callers. |
| `src/tools/web/` | Canonical web-provider boundary | Discovery/acquisition nodes consume its provider-neutral contracts. |
| `src/tools/firecrawl_tool.py` | Legacy Firecrawl client adapter | Used only behind `src/tools/web/firecrawl_provider.py` and direct compatibility tests. |
| `src/tools/BrowserTool.py`, `SearchTool.py`, `PdfTool.py`, `OCRTool.py`, `LlmsTool.py` | Legacy utility surface | No current canonical graph import; retained for compatibility and reviewed again in cleanup. |
| `docs/00_PROJECT_VISION.md` | Historical Turkish vision document | Architecture/rules/phase documents are the current English implementation sources of truth. |
| `venv/` | Legacy environment artifact | `.venv` plus `requirements-baseline.txt` is canonical; deletion remains deferred. |

No legacy surface was removed in Phase 26. The audit is intentionally
conservative because the project rules prohibit destructive cleanup without
whole-repository proof.
