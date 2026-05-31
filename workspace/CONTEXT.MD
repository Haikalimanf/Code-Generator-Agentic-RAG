# CONTEXT.MD — Workspace Layer 1 (ICM: Task Routing)

> **Interpretable Context Methodology (ICM) — Layer 1**
> File ini menjawab satu pertanyaan mendasar bagi agen AI:
> **"Ke mana saya harus pergi?"**
>
> Layer ini bertugas mengarahkan agen ke tahapan (stage), modul, atau sumber daya yang tepat
> berdasarkan jenis tugas yang diminta pengguna. Baca file ini **sebelum** membuka file lain.

---

## 1. Peta Tahapan Workspace

```
workspace/
├── CONTEXT.MD              ← Anda di sini (Layer 1: Task Router)
├── CLAUDE.md               ← Identitas sistem & panduan global untuk Claude Code
└── stages/
    └── 01_inceptions/
        └── CONTEXT.MD      ← Layer 2: Detail konteks fase inception (desain awal, scope)
```

> **Konvensi**: Setiap subfolder `stages/<nama-tahap>/` menyimpan konteks spesifik per
> fase pengembangan. Baca `stages/<nama-tahap>/CONTEXT.MD` saat bekerja di fase tersebut.

---

## 2. Routing Tugas — "Ke mana saya harus pergi?"

Gunakan tabel di bawah untuk memutuskan **di mana** tugas harus dikerjakan.

| Jika pengguna ingin... | Pergi ke... | File utama |
|---|---|---|
| Menambah / mengubah **agen baru** | `src/servers/` | `orchestrator.py` (tambah node & edge) |
| Mengubah **alur integrasi end-to-end** | `src/integration.py` | Step 1–3 di `run_full_integration_flow()` |
| Mengubah **skema Pydantic / model data** | `src/models/schemas.py` | `PlannerDecision`, `SpecialistTask`, dll. |
| Mengubah **konfigurasi environment** | `src/config/settings.py` | Singleton `settings` |
| Mengubah **utilitas bersama** (LLM, logging, error) | `src/utils/` | `llm_factory.py`, `error_handler.py`, `logging_config.py` |
| Mengubah **agen GitLab** (ekstraksi issue) | `src/agents/gitlab.py` | `run_gitlab_analyst_agent()` |
| Mengubah **RAG / PDF ingestion** | `src/servers/pdf_rag.py` & `src/ingest_pdf.py` | `run_compliance_expert_agent()` |
| Mengubah **Postman / Android / Figma agent** | `src/servers/<nama>.py` | Masing-masing: `postman.py`, `android_studio.py`, `figma.py` |
| Menambah **dokumen PDF** untuk RAG | `data/` → lalu jalankan ingest | `uv run python -m src.ingest_pdf` |
| Membaca **output hasil generate** | `outputs/` | `technical_context_issue_<N>.md` |
| Memahami **desain awal / inception** | `workspace/stages/inceptions/` | `CONTEXT.MD` |
| Memahami **identitas & arsitektur global** | `workspace/CLAUDE.md` | Seluruh file |

---

## 3. Alur Kerja Sistem (End-to-End)

Sistem ini berjalan dalam **3 langkah utama** yang didefinisikan di `src/integration.py`:

```
┌────────────────────────────────────────────────────────────────────────┐
│  STEP 1 — GitLab Agent                                                 │
│  src/agents/gitlab.py → run_gitlab_analyst_agent(project_id, issue_iid)│
│  Output: GitLabAnalysis (Pydantic) → requirement_spec (JSON string)    │
└─────────────────────────┬──────────────────────────────────────────────┘
                          │ requirement_spec
                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│  STEP 2 — Orchestrator (Planner-Executor, LangGraph)                   │
│  src/servers/orchestrator.py → get_complete_integration_context()      │
│                                                                        │
│  [supervisor_node]  → Planner LLM: dekomposisi tugas per agen          │
│        │                           (Context Engineering)               │
│        ▼ (dynamic routing)                                             │
│  [rag_node]         → RAG: cari pedoman coding di PGVector             │
│  [android_studio_node] (OFF) → Android project context                 │
│  [postman_node]        (OFF) → API contracts dari Postman              │
│  [figma_node]          (OFF) → Desain UI dari Figma                    │
│        │                                                               │
│        ▼ (fan-in)                                                      │
│  [consolidation_node] → Susun output Markdown akhir                    │
│                                                                        │
│  Output: Markdown string (Technical Integration Context Blueprint)     │
└─────────────────────────┬──────────────────────────────────────────────┘
                          │ final_context (Markdown)
                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│  STEP 3 — Format & Save                                                │
│  src/integration.py → outputs/technical_context_issue_<N>.md          │
└────────────────────────────────────────────────────────────────────────┘
```

> **Penting**: Orchestrator dipanggil **langsung (in-process)** dari `integration.py`,
> bukan sebagai MCP subprocess. Ini menghindari deadlock event loop FastMCP + LangGraph.

---

## 4. Agen Spesialis — Status & Cara Aktifkan

| Agen | Status | File | Cara Mengaktifkan |
|---|---|---|---|
| `rag` | ✅ **AKTIF** | `src/servers/pdf_rag.py` | Sudah aktif. Pastikan PGVector berjalan & PDF sudah di-ingest. |
| `gitlab` | ✅ **AKTIF** | `src/agents/gitlab.py` | Sudah aktif. Butuh `GITLAB_TOKEN`. |
| `android_studio` | ⏸ OFF | `src/servers/android_studio.py` | Cari `# <-- UNCOMMENT` di `orchestrator.py` & `schemas.py`. |
| `postman` | ⏸ OFF | `src/servers/postman.py` | Cari `# <-- UNCOMMENT` di `orchestrator.py` & `schemas.py`. Set `POSTMAN_API_KEY`. |
| `figma` | ⏸ OFF | `src/servers/figma.py` | Cari `# <-- UNCOMMENT` di `orchestrator.py` & `schemas.py`. Butuh Figma Desktop + `mcp-remote`. |

---

## 5. Sumber Daya Bersama (Shared Resources)

Sumber daya ini digunakan lintas agen. **Jangan duplikasi** — selalu rujuk dari lokasi berikut:

| Sumber Daya | Lokasi | Keterangan |
|---|---|---|
| **Konfigurasi & env vars** | `src/config/settings.py` | Singleton `settings`. Jangan panggil `os.getenv()` langsung. |
| **Pydantic schemas** | `src/models/schemas.py` | `PlannerDecision`, `SpecialistTask`, `GitLabAnalysis`, dll. |
| **LLM factory** | `src/utils/llm_factory.py` | `create_llm()`, `create_agent_with_memory()`, `execute_agent_and_structure()` |
| **Error handler** | `src/utils/error_handler.py` | `@wrap_tool_call`, `@wrap_async_tool_call` |
| **Logging** | `src/utils/logging_config.py` | Structured logging via modul `logging` Python |
| **Dokumen PDF (RAG)** | `data/` | Tambahkan PDF di sini, lalu jalankan `uv run python -m src.ingest_pdf` |
| **Output hasil** | `outputs/` | File Markdown per issue: `technical_context_issue_<N>.md` |
| **Cache Postman** | `postman_cache/` | Auto-generated, TTL 1 jam. Hapus folder untuk force refresh. |

---

## 6. Konvensi Koding yang Wajib Diikuti

Aturan ini berlaku di seluruh workspace. Lihat detail lengkap di `AGENTS.md` (root project).

- **Bahasa field Pydantic**: semua `description` field Pydantic ditulis dalam **Bahasa Indonesia**.
- **String user-facing**: deskripsi tool, system prompt, log message → dalam **Bahasa Indonesia**.
- **Structured output**: gunakan `method="function_calling"` dengan `with_structured_output()` untuk model dengan field `Optional`.
- **Pydantic strict**: model yang butuh OpenAI Structured Outputs wajib `ConfigDict(extra="forbid")`.
- **Config**: selalu `from src.config.settings import settings`. Dilarang `os.getenv()` langsung.
- **RAG bukan MCP**: panggil `run_compliance_expert_agent` via `asyncio.to_thread()`, bukan subprocess.

---

## 7. Titik Masuk (Entry Points) Sistem

```bash
# Jalankan seluruh alur integrasi (GitLab → Orchestrator → Output)
uv run python -m src.integration [PROJECT_ID] [ISSUE_IID]
# Default: project 81209841, issue #1

# Jalankan orchestrator sebagai MCP server standalone
uv run python -m src.servers.orchestrator

# Ingest dokumen PDF ke PGVector (wajib sebelum RAG berfungsi)
uv run python -m src.ingest_pdf

# Jalankan agen individual (saat diaktifkan)
uv run python -m src.servers.postman -- --api-key $POSTMAN_API_KEY
uv run python -m src.servers.android_studio -- --root /path/to/project
uv run python -m src.servers.figma -- --server
```

---

## 8. Catatan untuk Agen AI

> **Jika kamu (agen AI) membaca file ini**, ikuti urutan berikut sebelum mengerjakan tugas:
>
> 1. **Baca file ini sampai selesai** → pahami ke mana tugas harus diarahkan.
> 2. **Rujuk tabel routing (Bagian 2)** → tentukan file mana yang harus dibuka.
> 3. **Baca `workspace/CLAUDE.md`** → untuk identitas sistem dan arsitektur global.
> 4. **Baca `AGENTS.md` (root)** → untuk konvensi dan perintah siap pakai.
> 5. **Buka file target** → baru mulai analisis atau modifikasi.
>
> Jangan membuka `orchestrator.py` untuk tugas yang seharusnya ada di `schemas.py`,
> dan sebaliknya. Gunakan tabel routing di atas sebagai pemandu.
