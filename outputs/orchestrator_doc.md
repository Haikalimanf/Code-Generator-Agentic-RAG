# Dokumentasi: `src/servers/orchestrator.py`

## Ringkasan
File `orchestrator.py` mengimplementasikan **Integration Orchestrator** berbasis **Planner-Executor Architecture** menggunakan **LangGraph**. Modul ini bertugas menerima *requirement* (contoh: GitLab issue atau user story) dan secara otomatis merencanakan serta mendelegasikan tugas ke agen-agen spesialis (RAG, Android Studio, Postman, Figma) menggunakan prinsip *Context Engineering*.

## Arsitektur & Prinsip Utama
1. **Planner-Executor Architecture**: Terdapat sebuah Supervisor (Planner) yang menganalisis kebutuhan dan membuat instruksi spesifik, serta Executor (agen spesialis) yang menjalankan instruksi tersebut.
2. **Context Engineering**: Memastikan setiap agen hanya menerima instruksi dan konteks yang relevan dengan domainnya. Planner tidak meneruskan *user story* secara mentah, melainkan melakukan dekomposisi tugas yang fokus per domain untuk mengoptimalkan penggunaan token dan akurasi *output*.
3. **Dynamic Routing**: Berdasarkan keputusan *Structured Output LLM* pada Planner, *Graph* akan melakukan *fan-out* secara paralel ke node-node spesialis yang dituju, dan kemudian melakukan *fan-in* ke *Consolidation Node* untuk dikumpulkan hasilnya.

## Agen Spesialis (Specialist Agents)
Saat ini pada kode, hanya agen **RAG (Compliance Expert)** yang aktif (karena dipanggil secara *in-process* melalui `asyncio.to_thread`). Agen MCP lainnya telah disediakan konfigurasinya dan dapat diaktifkan dengan menghapus komentar (`# <-- UNCOMMENT`) pada blok terkait.

- **`rag`** (Aktif): Mengambil pedoman coding, standar perusahaan, dan *best practices* dari dokumen internal.
- **`android_studio`** (Opsional): Menganalisis struktur kode proyek Android dan pola arsitektur.
- **`postman`** (Opsional): Menganalisis API contracts dan endpoint HTTP.
- **`figma`** (Opsional): Menganalisis desain UI/UX dari Figma menjadi bentuk XML metadata.

## Komponen LangGraph (`StateGraph`)
Proses orkestrasi didefinisikan menggunakan `StateGraph` dengan alur:
`START → supervisor_node → [specialist_nodes] → consolidation_node → END`

- **`OrchestratorState`**: `TypedDict` yang menyimpan *state* global *graph* (berisi: *requirement, agent_plan, code_structure, api_contracts, design_context, company_guidelines, errors, consolidated_output*).
- **`supervisor_node`**: Node LLM Planner yang mengekstraksi *story* dan memecahnya menjadi `PlannerDecision` (instruksi unik per agen).
- **`rag_node` / *Specialist Nodes***: Mengeksekusi tugas pada agen berdasarkan instruksi dari Planner.
- **`consolidation_node`**: Menyusun *output* akhir dari semua agen spesialis menjadi format Markdown yang siap disajikan ke *user* atau LLM utama.

## FastMCP Tools yang Diekspos
File ini menggunakan `FastMCP` (nama server `IntegrationOrchestrator`) untuk mengekspos kemampuan *orchestrator* sebagai *tools* MCP:

1. **`get_complete_integration_context(requirement, ...)`**
   - **Fungsi**: Memulai alur kerja *Planner-Executor*. Menerima *requirement* sistem dan mengembalikan laporan teknis integrasi secara lengkap dalam format Markdown. (Parameter boolean lama seperti *include_api* telah *deprecated* karena *routing* kini otonom).
2. **`query_rag_directly(query)`**
   - **Fungsi**: Memungkinkan *query* secara langsung ke sistem RAG tanpa melewati proses *Planner/Graph*. Berguna untuk pengecekan instan.
3. **`health_check_all_servers()`**
   - **Fungsi**: Memeriksa status (*health check*) dan ketersediaan dari seluruh agen MCP dan RAG, mengembalikan data diagnostik (*ONLINE/OFFLINE*, beserta rincian *error*-nya).
