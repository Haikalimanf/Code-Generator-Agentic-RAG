# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **Android Development Automation System** using multiple MCP (Model Context Protocol) servers to coordinate code generation workflows. The system extracts requirements from GitLab issues, gathers context from multiple sources (Postman APIs, Android project structure, Kotlin docs, company PDF guidelines), and provides aggregated context for AI code generation.

## Architecture

The project follows a modular package structure:

```
src/
├── config/           # Centralized configuration
│   └── settings.py   # Single source of truth for env vars and paths
├── models/           # Pydantic schemas (shared across all agents)
│   └── schemas.py     # GitLabAnalysis, PostmanAPIAnalysis, etc.
├── utils/            # Shared utilities
│   ├── logging_config.py   # Structured logging via logging module
│   ├── error_handler.py    # wrap_tool_call / wrap_async_tool_call
│   └── llm_factory.py      # create_llm, create_agent_with_memory, execute_agent_and_structure
├── agents/           # Standalone agents (no MCP server)
│   └── gitlab.py     # GitLab issue extraction agent
├── servers/          # MCP servers and services
│   ├── orchestrator.py      # Main orchestrator MCP server
│   ├── postman.py            # Postman API collections MCP server
│   ├── android_studio.py     # Android project context MCP server
│   ├── figma.py              # Figma design context MCP server
│   ├── context7.py           # Kotlin documentation via Context7
│   └── pdf_rag.py            # RAG chain for company PDFs (direct import)
├── integration.py    # Full workflow demo: GitLab -> Orchestrator
└── ingest_pdf.py     # PDF ingestion utility
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run orchestrator
uv run python -m src.servers.orchestrator

# Run integration example
uv run python -m src.integration

# Individual MCP servers
uv run python -m src.servers.postman -- --api-key $POSTMAN_API_KEY
uv run python -m src.servers.android_studio -- --root /path/to/android/project
uv run python -m src.servers.figma -- --server

# Ingest PDF documents
uv run python -m src.ingest_pdf
```

## Key Design Decisions

1. **Centralized config**: All env vars read once in `src/config/settings.py`. No more scattered `os.getenv()` calls.
2. **Shared schemas**: All Pydantic models in `src/models/schemas.py`. No duplicate model definitions.
3. **Shared utilities**: `wrap_tool_call`, `create_llm`, `create_agent_with_memory`, `execute_agent_and_structure` in `src/utils/`. No more copy-pasting.
4. **Structured logging**: Uses Python `logging` module instead of `print(..., file=sys.stderr)`.
5. **RAG Architecture**: PDF RAG uses PostgreSQL with pgvector. Orchestrator imports `run_compliance_expert_agent` directly from `src.servers.pdf_rag` -- not as MCP.

## Environment Variables

Set these in `.env`:

```bash
# LLM (via OpenRouter)
OPENROUTER_API_KEY=your_key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
MODEL_NAME=anthropic/claude-sonnet-4.5

# GitLab
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_token

# PostgreSQL Vector DB
VECTOR_DATABASE_URL=postgresql://user:pass@host:port/dbname

# Postman (optional)
POSTMAN_API_KEY=your_key
POSTMAN_WORKSPACE_ID=your_workspace

# Android Project (optional, can use --root arg)
ANDROID_PROJECT_ROOT=/path/to/android/project
```

## Important Implementation Details

### MCP Server Pattern
All MCP servers use `fastmcp.FastMCP` with `stdio` transport. Tools are decorated with `@mcp.tool()`. Servers run with `mcp.run(transport="stdio")`.

### Agent Pattern
Agents use `langgraph.prebuilt.create_react_agent` or `langchain.agents.create_agent` with `langchain_mcp_adapters.client.MultiServerMCPClient`. The `execute_agent_and_structure` helper in `src/utils/llm_factory.py` standardizes the pattern of streaming agent output then converting to Pydantic structured output.

### Collection Name
The vectorstore collection is configured via `RAG_COLLECTION_NAME` env var (default: `company_guidelines`).