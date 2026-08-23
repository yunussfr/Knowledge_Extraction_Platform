# Knowledge Extraction Platform Agent Index

Canonical project documents:

- `docs/RULES.md` — mandatory engineering and safety rules.
- `docs/PHASES.md` — ordered phase roadmap and acceptance gates.
- `docs/DEVELOPMENT_PROGRESS.md` — verified implementation boundary and phase record.
- `docs/ARCHITECTURE.md` — intended architecture and contracts.

Canonical environment and checks:

- Use `.venv\Scripts\python.exe` and `requirements-baseline.txt`.
- Offline regression: `.venv\Scripts\python.exe -m pytest -q`.
- Compile check: `.venv\Scripts\python.exe -m compileall -q src scripts tests`.
- Live Crawl4AI tests are opt-in and use only local fixtures.

Architecture map:

- LangGraph orchestration: `src/agents/graphs/phase2_pipeline.py`.
- Serializable state: `src/state/state.py`.
- Pydantic contracts: `src/schemas/models.py`.
- Web provider boundary: `src/tools/web/`.
- Structured provider boundary: `src/tools/structured_generation/`.
- Evidence, validation, resolution, deduplication, and profiles: `src/agents/nodes/`.

Operational reminders:

- Preserve SourcePolicy optional semantics, provenance, exact evidence, and no-fabrication rules.
- Do not edit owner-managed prompt wording or implement deferred research intelligence.
- Use targeted navigation; update `docs/DEVELOPMENT_PROGRESS.md` after every phase.
- Checkpoint artifacts are resumable user artifacts; do not delete them or perform destructive Git operations.
