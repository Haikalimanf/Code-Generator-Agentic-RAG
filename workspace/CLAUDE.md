# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🪪 Identitas Global — "Siapa Saya?"

**Nama Sistem**: Android Development Automation System
**Dibuat oleh**: Haikalimanf
**Tujuan utama**: Mengotomatisasi alur kerja pengembangan Android dengan cara mengekstrak kebutuhan dari GitLab, mengumpulkan konteks dari berbagai sumber, lalu menghasilkan panduan kode yang siap pakai bagi AI code generation.

### Apa yang dilakukan sistem ini?

Sistem ini berperan sebagai **Planner-Executor agentic pipeline** berbasis [LangGraph](https://github.com/langchain-ai/langgraph). Ia:

1. **Membaca GitLab Issue** → Mengekstrak user story dan persyaratan teknis secara terstruktur.
2. **Mengumpulkan konteks multi-sumber** → Dari Postman (API schema), Android Studio (struktur project), Figma (desain UI), Context7 (dokumentasi Kotlin), dan PDF perusahaan (aturan internal via RAG).
3. **Merencanakan tugas per agen** → Planner LLM membagi pekerjaan ke agen-agen spesialis (bukan mengirim raw user story).
4. **Menghasilkan output Markdown** → Berupa panduan kode yang siap dikonsumsi oleh AI coding assistant.

### Siapa yang menggunakannya?

- **Developer Android** yang ingin mempercepat proses code generation berbasis issue.
- **AI coding assistant** (termasuk Claude) yang membutuhkan konteks yang kaya dan terstruktur sebelum menulis kode.

### Teknologi inti

| Komponen | Teknologi |
|---|---|
| Orkestrasi agen | LangGraph `StateGraph` |
| LLM | OpenRouter (default: `openai/gpt-4.1`) |
| Protokol antar agen | MCP (Model Context Protocol) via `fastmcp` |
| Vector store (RAG) | PostgreSQL + pgvector |
| Embedding model | `sentence-transformers/all-MiniLM-L6-v2` |
| Manajemen konfigurasi | `pydantic-settings` (singleton `settings`) |
| Package manager | `uv` |

---

## Project Overview

This is an **Android Development Automation System** using multiple MCP (Model Context Protocol) servers to coordinate code generation workflows. The system extracts requirements from GitLab issues, gathers context from multiple sources (Postman APIs, Android project structure, Kotlin docs, company PDF guidelines), and provides aggregated context for AI code generation.

## Architecture

Sistem mengikuti pola **Planner-Executor** dengan `LangGraph StateGraph`:

```
GitLab Issue → GitLabAgent → Planner LLM → [RAG / Postman / Android / Figma] → Konsolidasi → Output Markdown
```

### Struktur Folder

```
Membuat MCP Server/               ← Root project
│
├── .env                          # Environment variables (tidak di-commit)
├── .python-version               # Versi Python (3.10)
├── pyproject.toml                # Dependency & metadata project
├── uv.lock                       # Lock file uv
├── AGENTS.md                     # Panduan agent untuk AI coding assistant
├── README.md                     # Dokumentasi publik
├── ICM_GUIDELINE.md              # Panduan Interpretable Context Methodology (ICM) untuk stages/
│
├── src/                          # Source code utama
│   ├── __init__.py
│   ├── integration.py            # Demo alur penuh: GitLab → Orchestrator
│   ├── ingest_pdf.py             # Utilitas ingest PDF ke PGVector
│   │
│   ├── config/                   # Konfigurasi terpusat
│   │   ├── __init__.py
│   │   └── settings.py           # Singleton settings (baca .env sekali)
│   │
│   ├── models/                   # Pydantic schemas (dibagi ke semua agen)
│   │   ├── __init__.py
│   │   └── schemas.py            # GitLabAnalysis, PlannerDecision, dll.
│   │
│   ├── utils/                    # Utilitas bersama
│   │   ├── __init__.py
│   │   ├── logging_config.py     # Structured logging via modul logging
│   │   ├── error_handler.py      # wrap_tool_call / wrap_async_tool_call
│   │   └── llm_factory.py        # create_llm, create_agent_with_memory, execute_agent_and_structure, load_stage_prompt
│   │
│   ├── agents/                   # Agen standalone (bukan MCP server)
│   │   ├── __init__.py
│   │   └── gitlab.py             # Agen ekstraksi GitLab issue (dengan uncertainty sampling)
│   │
│   └── servers/                  # MCP servers & layanan
│       ├── __init__.py
│       ├── orchestrator.py       # Orchestrator utama (Planner-Executor)
│       ├── postman.py            # MCP server: Postman API collections
│       ├── android_studio.py     # MCP server: konteks project Android
│       ├── figma.py              # MCP server: konteks desain Figma
│       ├── context7.py           # MCP server: dokumentasi Kotlin via Context7
│       └── pdf_rag.py            # RAG chain untuk PDF perusahaan (direct import)
│
├── data/                         # Dokumen PDF sumber untuk RAG
├── outputs/                      # (Legacy) Output Markdown hasil generate
├── postman_cache/                # Cache response Postman API (TTL 1 jam)
├── experiment/                   # Modul eksperimental
│   └── uncertainty/
│       └── semantic_clustering.py  # Digunakan oleh gitlab.py
│
├── council_sessions/             # (Eksperimental) log sesi council agent
│
└── workspace/                    # Dokumentasi & konteks kerja
    ├── CLAUDE.md                 # ← File ini
    ├── CONTEXT.MD                # Konteks tingkat tinggi project (Layer 1)
    └── stages/
        └── 01_inceptions/
            ├── CONTEXT.MD        # Konteks fase inception (Layer 2)
            ├── reference/        # Panduan & template stabil (Layer 3)
            │   └── blueprint_template.md
            └── output/           # Artefak hasil kerja dinamis (Layer 4)
                └── technical_blueprint.md
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