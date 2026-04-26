# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **Android Development Automation System** using multiple MCP (Model Context Protocol) servers to coordinate code generation workflows. The system extracts requirements from GitLab issues, gathers context from multiple sources (Postman APIs, Android project structure, Kotlin docs, company PDF guidelines), and provides aggregated context for AI code generation.

## Architecture

The system uses a multi-agent orchestration pattern with 4 main context sources:

1. **GitLab Agent** (`agent_gitlab.py`) - Fetches requirements from GitLab issues
2. **Integration Orchestrator** (`orchestrator.py`) - Coordinates 3 MCP servers + direct RAG access:
   - Postman MCP (`postman_context_server.py`) - API contracts and endpoint schemas
   - Android Studio MCP (`agent_context_android_studio.py`) - Project structure and source code
   - Context7 MCP (`agent_context_7.py`) - Kotlin/Android documentation via Upstash Context7
   - Figma MCP (`figma_context_server.py`) - Design specifications and XML metadata
   - PDF RAG (`agent_pdf_rag.py`) - Company documents and coding standards (direct import, not MCP)

3. **Integration Example** (`integration.py`) - Demonstrates full workflow: GitLab → Orchestrator → Code Generator

## Common Commands

This project uses **UV** as the Python package manager:

```bash
# Install dependencies
uv sync

# Run a script
uv run src/orchestrator.py
uv run src/integration.py

# Run with arguments
uv run src/postman_context_server.py --api-key $POSTMAN_API_KEY
uv run src/agent_context_android_studio.py --root /path/to/android/project
uv run src/figma_context_server.py

# Ingest PDF documents
uv run src/ingest_pdf.py
```

## Key Files and Their Roles

| File | Purpose |
|------|---------|
| `src/orchestrator.py` | Main MCP server that coordinates all context sources. Run this first in a terminal. |
| `src/integration.py` | Example client that connects to orchestrator and demonstrates full workflow |
| `src/agent_gitlab.py` | Standalone agent to extract requirements from GitLab issues |
| `src/postman_context_server.py` | MCP server for Postman API collections (cloud or local JSON) |
| `src/agent_context_android_studio.py` | MCP server to read Android project files, structure, manifests |
| `src/figma_context_server.py` | MCP server for Figma design context and XML metadata |
| `src/agent_context_7.py` | MCP server for Kotlin documentation via Context7 |
| `src/agent_pdf_rag.py` | Direct RAG chain for company PDFs (imported by orchestrator) |
| `src/ingest_pdf.py` | Utility to ingest PDFs into PostgreSQL vector store |

## Environment Variables

The following must be set in `.env`:

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

## Development Workflow

**To test the full integration:**

1. **Terminal 1** - Start the orchestrator MCP server:
   ```bash
   uv run src/orchestrator.py
   ```

2. **Terminal 2** - Run the integration example:
   ```bash
   uv run src/integration.py
   ```

**To use individual MCP servers:**

```bash
# Postman (with local JSON)
uv run src/postman_context_server.py --collection-json /path/to/collection.json

# Postman (with cloud API)
uv run src/postman_context_server.py --api-key $POSTMAN_API_KEY

# Android Studio context
uv run src/agent_context_android_studio.py --root /path/to/android/project

# Figma design context
uv run src/figma_context_server.py
```

## Important Implementation Details

### MCP Server Pattern
All MCP servers use `fastmcp.FastMCP` with `stdio` transport. Tools are decorated with `@mcp.tool()`. Servers run with `mcp.run(transport="stdio")`.

### RAG Architecture
The PDF RAG uses PostgreSQL with pgvector (via `langchain_postgres.PGVector`). The orchestrator imports `rag_chain` directly from `agent_pdf_rag.py` - it does NOT run as an MCP server but is imported as a module.

### Agent Pattern
Agents use `langgraph.prebuilt.create_react_agent` with `langchain_mcp_adapters.client.MultiServerMCPClient`. Example:

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

async with MultiServerMCPClient(config) as client:
    tools = await client.get_tools()
    agent = create_react_agent(llm, tools)
    response = await agent.ainvoke({"messages": [...]})
```

### Collection Name
The vectorstore collection is named `permenpan_index_v3` (defined in `agent_pdf_rag.py` and `ingest_pdf.py`).
