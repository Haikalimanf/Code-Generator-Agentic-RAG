# AGENTS.md

## Quick Reference

```bash
# Install
uv sync

# Run orchestrator (RAG-only, other agents commented out)
uv run python -m src.servers.orchestrator

# Run full integration: GitLab Agent → Orchestrator → RAG
uv run python -m src.integration [PROJECT_ID] [ISSUE_IID]
# Default: project 81209841, issue #1

# Ingest PDFs into PGVector (must run before RAG works)
uv run python -m src.ingest_pdf

# Individual MCP servers (when re-enabled)
uv run python -m src.servers.postman -- --api-key $POSTMAN_API_KEY
uv run python -m src.servers.android_studio -- --root /path/to/project
uv run python -m src.servers.figma -- --server

# Direct RAG query (bypasses orchestrator)
# Use query_rag_directly() tool on orchestrator
```

## Required Environment

`.env` must contain at minimum `OPENROUTER_API_KEY`. Other variables:

```
OPENROUTER_API_KEY=       # Required. LLM via OpenRouter.
OPENROUTER_BASE_URL=      # Default: https://openrouter.ai/api/v1
MODEL_NAME=               # Default: openai/gpt-4.1
VECTOR_DATABASE_URL=       # Required for RAG. postgresql://user:pass@host:port/dbname
GITLAB_URL=                # Default: https://gitlab.com
GITLAB_TOKEN=              # Required for GitLab agent
POSTMAN_API_KEY=           # Optional. Enables Postman agent
POSTMAN_WORKSPACE_ID=      # Optional
ANDROID_PROJECT_ROOT=      # Optional. Path to Android project
FIGMA_MCP_URL=             # Default: http://127.0.0.1:3845/sse
RAG_COLLECTION_NAME=        # Default: company_guidelines
RAG_EMBEDDING_MODEL=        # Default: sentence-transformers/all-MiniLM-L6-v2
POSTMAN_COLLECTION_JSON=   # Optional. Local JSON file as alternative to API
```

## Architecture

Planner-Executor pattern using LangGraph StateGraph:

```
GitLab Issue → GitLabAgent → Planner LLM → [RAG specialist] → Consolidation → Markdown output
```

- **Planner** (`supervisor_node`): Decomposes user story into focused tasks per agent (Context Engineering). Each agent gets a unique plan, NOT the raw user story.
- **RAG specialist** (`rag_node`): Calls `run_compliance_expert_agent` directly in-process (not via MCP subprocess).
- **Other agents** (Android Studio, Postman, Figma): Full implementations exist but are **commented out** in orchestrator.py. Re-enable by searching `# <-- UNCOMMENT` in orchestrator.py and schemas.py.

### Key Pattern: Context Engineering

`PlannerDecision` in schemas.py uses explicit `Optional[SpecialistTask]` fields per agent (not `Dict[str, T]`) because OpenAI Structured Outputs rejects `additionalProperties`. When adding new agents, add an `Optional[SpecialistTask]` field to `PlannerDecision` and uncomment the corresponding node/edge in orchestrator.py.

### How Agents Work

- **MCP servers**: Use `fastmcp.FastMCP` with `@mcp.tool()`, run with `mcp.run(transport="stdio")`.
- **Tool decoration**: `@tool` (LangChain) + `@mcp.tool()` (FastMCP) + `@wrap_tool_call` (error handler).
- **Agent creation**: `create_agent_with_memory()` → LangGraph agent with MemorySaver → `execute_agent_and_structure()` streams output then structures via `llm.with_structured_output()`.
- **GitLab agent only**: Two-phase uncertainty sampling (5 samples at temp=1.0, semantic clustering, entropy threshold 0.4). Escalates to GitLab comment if ambiguous.

## Critical Conventions

- **All Pydantic field descriptions are in Indonesian** (Bahasa Indonesia). Keep this consistent.
- **All user-facing strings** (tool descriptions, system prompts, log messages) are in Indonesian.
- **Pydantic strictness**: Models that need OpenAI Structured Outputs must use `ConfigDict(extra="forbid")`. The `additionalProperties: false` pattern is required.
- **Structured output method**: Use `method="function_calling"` with `with_structured_output()` for `PlannerDecision` (or any model with Optional fields). The default `"json_schema"` method rejects Optional fields on some providers.
- **RAG is direct import**, not MCP subprocess: `from src.servers.pdf_rag import run_compliance_expert_agent`. Called via `asyncio.to_thread()`.
- **Config is singleton**: Always `from src.config.settings import settings`. Never call `os.getenv()` directly.

## Testing

No test suite exists. No pytest, no test directory, no CI. Verify changes by running orchestrator or integration commands directly.

## Known Gotchas

- **No linter/formatter configured.** No ruff, mypy, black, or pre-commit hooks exist.
- **Python 3.10+ required** (`.python-version` says 3.10, `pyproject.toml` says `>=3.10`).
- **PGVector must be running** before RAG queries work. Run `uv run python -m src.ingest_pdf` after any PDF changes in `data/`.
- **Postman caching**: API responses cached in `postman_cache/` with 1-hour TTL. Delete the directory to force refresh.
- **Figma requires Figma Desktop App** running with Dev Mode enabled, plus `mcp-remote` npm package.
- **GitLab agent imports from `experiment.uncertainty.semantic_clustering`** — this is not a standard package, it's local code in `experiment/`.
- **llm_factory.py uses `langchain.agents.create_agent`** (not `langgraph.prebuilt.create_react_agent`). Both patterns exist in the codebase — `figma.py` uses `langchain.agents.create_agent`, most others use `langgraph`.