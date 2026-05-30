# Technical Blueprint — Inception Stage Factory

> **Peran file ini**: "Pabrik" aturan baku yang **stabil dan tidak berubah** setiap eksekusi.
> File ini mendefinisikan **standar ekstraksi** dan **format output** yang harus dipatuhi
> oleh semua agen yang bertugas mengumpulkan data di fase Inception.
>
> Dibaca oleh: Orchestrator Agent, Specialist Nodes, dan siapapun yang menambahkan agen baru.

---

## Bagian 1 — Kontrak Output Global

Setiap agen **wajib** menghasilkan output yang dapat dikonversi ke Pydantic model.
Semua model berada di `src/models/schemas.py`. Daftar berikut adalah kontrak yang tidak boleh diubah
tanpa memperbarui **semua konsumen** model tersebut (orchestrator, integration, consolidation_node).

| Agen | Fungsi Utama | Output Schema | Metode Serialisasi |
|---|---|---|---|
| **GitLab** | Ekstraksi & validasi user story | `GitLabAnalysis` | `.model_dump_json(indent=2)` |
| **Postman** | API contract & endpoint discovery | `PostmanAPIAnalysis` | `.model_dump_json(indent=2)` |
| **Android Studio** | Struktur proyek & arsitektur kode | `AndroidArchitectureAnalysis` | `.model_dump_json(indent=2)` |
| **Figma** | Metadata XML desain UI | `FigmaDesignAnalysis` | `.model_dump_json(indent=2)` |
| **RAG / PDF** | Pedoman coding perusahaan | `ComplianceAnalysis` | `.model_dump_json(indent=2)` |

> **Aturan**: Semua model Pydantic yang menggunakan OpenAI Structured Outputs **wajib** memiliki
> `ConfigDict(extra="forbid")`. Model `GitLabAnalysis` adalah pengecualian (tidak wajib).

---

## Bagian 2 — Standar Ekstraksi Per Agen

### 2.1 Agen GitLab (`src/agents/gitlab.py`)

**Tujuan**: Mengubah GitLab Issue menjadi satu User Story terstruktur yang deterministik.

#### Aturan Ekstraksi

```
SUMBER DATA:
  - issue.title           → konteks nama fitur
  - issue.description     → narasi utama requirement
  - issue.comment         → komentar diskusi tim (bukan sistem)
  
YANG DIABAIKAN:
  - Komentar sistem (note.system == True)
  - Metadata GitLab lainnya (assignee, milestone, dll)
```

#### Format User Story yang Wajib Diikuti

```
"As a mobile developer, I want [goal], so that [benefit]."

Aturan field:
  role    → SELALU "mobile developer" (baku, tidak berubah)
  goal    → Dimulai dengan KATA KERJA AKTIF (implement, build, create, integrate, ...)
  benefit → Menjelaskan "mengapa" ini penting bagi developer/tim (bukan end-user)
  story   → Gabungan role + goal + benefit dalam format baku di atas
```

#### Contoh Output Valid

```json
{
  "role": "mobile developer",
  "goal": "implement a user authentication flow using JWT tokens",
  "benefit": "ensure secure access control and maintain session persistence across app restarts",
  "story": "As a mobile developer, I want to implement a user authentication flow using JWT tokens, so that I can ensure secure access control and maintain session persistence across app restarts."
}
```

#### Contoh Output Tidak Valid ❌

```
❌ role: "user" atau "customer" atau "admin"
   → role selalu "mobile developer"

❌ goal: "login feature implemented"
   → goal harus dimulai kata kerja aktif, bukan kata benda

❌ story yang menyebutkan nama class, file, atau teknologi spesifik
   tanpa referensi eksplisit dari issue
   → jangan menebak implementasi teknis
```

#### Kontrol Kualitas — Uncertainty Pre-Check

Sistem menjalankan **5 sampel** (temperature=1.0) sebelum eksekusi deterministik.
Jika `normalized_entropy > 0.400`, pipeline **wajib dihentikan** dan komentar eskalasi dikirim ke GitLab.

```
Rumus entropy:
  entropy = Σ -p(cluster_i) × log(p(cluster_i))
  normalized_score = entropy / log(M)     ← M = jumlah sampel (5)
  
Threshold: 0.400
  ≤ 0.400 → CONFIDENT → lanjut ke Fase 2 deterministik
  > 0.400 → UNCERTAIN → eskalasi + raise ValueError
```

---

### 2.2 Agen Postman (`src/servers/postman.py`)

**Tujuan**: Menemukan dan mengekstrak API contract yang relevan dengan fitur dari koleksi Postman.

#### Sumber Data (Dua Mode)

```
MODE 1 — Postman Cloud API (prioritas utama):
  Endpoint: https://api.getpostman.com/collections
  Auth: X-Api-Key header (dari POSTMAN_API_KEY)
  Caching: postman_cache/<cache_key>.json, TTL = 3600 detik (1 jam)
  Limit: Maksimal 10 collection pertama

MODE 2 — Local JSON File (fallback):
  Sumber: POSTMAN_COLLECTION_JSON (path file .json Postman export)
  Digunakan jika POSTMAN_API_KEY tidak ada
```

#### Algoritma Pemilihan Endpoint

```
1. Tokenisasi feature_description (pisah whitespace + tanda baca)
2. Hapus stop words: {dan, the, for, with, yang, dari, ke, di, dengan, atau, and, or, to}
3. Hitung skor per endpoint:
   score = jumlah token yang muncul di (name + url + folder_path + description)
4. Ambil TOP 10 endpoint berdasarkan skor tertinggi
5. Jika tidak ada match → kembalikan pesan "tidak ditemukan"
```

#### Format Output Wajib (PostmanAPIAnalysis)

```json
{
  "feature_summary": "Ringkasan singkat fitur yang dianalisis",
  "relevant_endpoints": [
    "POST /api/v1/auth/login — Autentikasi user dan mendapatkan JWT token",
    "POST /api/v1/auth/refresh — Perbarui access token menggunakan refresh token",
    "DELETE /api/v1/auth/logout — Invalidate session user"
  ],
  "api_contracts": [
    "POST /api/v1/auth/login\n  Body: {\"email\": string, \"password\": string}\n  Response 200: {\"token\": string, \"refresh_token\": string}",
    "POST /api/v1/auth/refresh\n  Body: {\"refresh_token\": string}\n  Response 200: {\"token\": string}"
  ],
  "missing_endpoints": [
    "Endpoint untuk reset password tidak ditemukan di collection"
  ],
  "recommendations": "Pastikan token disimpan di EncryptedSharedPreferences, bukan SharedPreferences biasa."
}
```

#### Aturan Ekstraksi

```
YANG DIEKSTRAK per endpoint:
  - method           (GET/POST/PUT/PATCH/DELETE)
  - url.raw          (URL lengkap dengan variable)
  - url.query[]      (query parameters yang aktif)
  - request.header[] (header selain Authorization)
  - request.body     (raw JSON / urlencoded / formdata)
  - response[0]      (contoh response HTTP 2xx pertama)
  - path params      (pattern {variable} dalam URL)

YANG DIABAIKAN:
  - Header Authorization (sensitif)
  - Disabled query params (disabled: true)
  - Disabled headers
  - Response non-2xx (diabaikan untuk brevity, kecuali diminta eksplisit)
```

---

### 2.3 Agen Android Studio (`src/servers/android_studio.py`)

**Tujuan**: Memahami struktur, arsitektur, dan dependency proyek Android yang sedang dikerjakan.

#### Scope File yang Diperbolehkan

```
Ekstensi yang dibaca:
  .kt, .java, .xml, .gradle, .kts, .properties, .json, .md, .txt, .pro, .toml

Direktori yang dilewati (auto-skip):
  .git, .gradle, .idea, build, node_modules, __pycache__,
  .DS_Store, intermediates, generated, tmp, cache

Batas ukuran file: 500 KB per file
Batas hasil pencarian: 50 hits
Kedalaman pohon folder: maksimal 5 level
```

#### Tools yang Tersedia dan Kapan Digunakan

| Tool | Kapan Digunakan |
|---|---|
| `list_android_modules()` | Langkah pertama — temukan modul yang ada |
| `get_project_structure(max_depth=3)` | Gambar besar struktur folder |
| `analyze_manifest(module_path)` | Pahami komponen, permission, SDK target |
| `list_files_in_module(module_path)` | Inventarisasi file per modul |
| `read_source_file(path)` | Baca implementasi spesifik |
| `search_code(query)` | Temukan pattern / class / interface tertentu |
| `get_gradle_dependencies(module_path)` | Identifikasi library yang digunakan |

#### Urutan Eksplorasi yang Disarankan

```
1. list_android_modules()           → temukan daftar modul
2. get_project_structure(depth=3)   → pahami layout folder
3. analyze_manifest("app")          → komponen, permission, SDK
4. get_gradle_dependencies("app")   → dependency utama
5. search_code("ViewModel")         → cari pola arsitektur
6. read_source_file(<file krusial>) → baca detail implementasi
```

#### Format Output Wajib (AndroidArchitectureAnalysis)

```json
{
  "overview": "Proyek Android multi-modul dengan arsitektur MVVM + Clean Architecture. Modul: app, core, feature/auth.",
  "key_components": [
    "app/MainActivity.kt — Entry point, navigasi utama",
    "core/network/ApiService.kt — Interface Retrofit untuk semua API call",
    "feature/auth/AuthViewModel.kt — ViewModel untuk alur autentikasi"
  ],
  "data_flow": "UI (Fragment) → ViewModel → Repository → DataSource (Remote/Local) → Room/Retrofit",
  "relevant_files": [
    "app/src/main/java/com/example/auth/AuthViewModel.kt",
    "core/network/src/main/java/com/example/core/ApiService.kt",
    "app/src/main/AndroidManifest.xml"
  ],
  "architectural_patterns": [
    "MVVM (ViewModel + LiveData/StateFlow)",
    "Repository Pattern",
    "Clean Architecture (domain layer terpisah)",
    "Dependency Injection (Hilt)"
  ],
  "recommendations": "Pertimbangkan menggunakan WorkManager untuk operasi background yang membutuhkan guarantees."
}
```

#### Aturan Ekstraksi

```
FOKUS UTAMA:
  - Pola arsitektur yang terdeteksi (MVVM, Clean Arch, MVI, dll)
  - Komponen krusial dan relasi antar komponen
  - Library DI yang digunakan (Hilt, Koin, manual)
  - Versi SDK (minSdk, targetSdk, compileSdk)
  
YANG TIDAK PERLU DIEKSTRAK:
  - Isi file XML layout secara verbatim (cukup ringkasan)
  - Seluruh daftar dependency (cukup yang relevan dengan fitur)
  - Kode boilerplate standar Android
```

---

### 2.4 Agen Figma (`src/servers/figma.py`)

**Tujuan**: Mengekstrak metadata XML desain UI dari Figma untuk memandu implementasi layout Android.

#### Prasyarat Wajib

```
✅ Figma Desktop App harus terbuka
✅ Dev Mode harus diaktifkan di Figma
✅ mcp-remote npm package harus terpasang
✅ FIGMA_MCP_URL harus dapat diakses (default: http://127.0.0.1:3845/sse)
```

#### Peta Node yang Sudah Diketahui

```python
KNOWN_NODES = {
    "login"    : "2335:6376",
    "register" : "2335:6404",
    "chat"     : "2335:5716",
    "home"     : "2335:5799",
}
```

> **Konvensi**: Saat menambahkan layar baru, tambahkan mapping ke `KNOWN_NODES` di `figma.py`
> **DAN** ke `FIGMA_NODE_MAP` di `orchestrator.py`.

#### Alur Ekstraksi yang Disarankan

```
1. Panggil get_metadata() TANPA nodeId → dapatkan peta halaman
2. Identifikasi nodeId yang sesuai dengan fitur
3. Panggil get_metadata(nodeId=<id>) → XML metadata detail
4. Opsional: get_design_context(nodeId) → screenshot + reference code
```

#### Format Output Wajib (FigmaDesignAnalysis)

```json
{
  "feature_name": "Login Screen",
  "node_id": "2335:6376",
  "structure_summary": "LinearLayout vertikal dengan logo di atas, dua EditText (email, password), tombol Login, dan link 'Lupa Password'.",
  "key_components": [
    {"id": "2335:6377", "name": "EmailInput", "type": "EditText", "hint": "Masukkan email"},
    {"id": "2335:6378", "name": "PasswordInput", "type": "EditText", "inputType": "textPassword"},
    {"id": "2335:6379", "name": "LoginButton", "type": "Button", "text": "Masuk"}
  ],
  "xml_context": "<LinearLayout android:orientation=\"vertical\">\n  <EditText android:id=\"@+id/emailInput\" .../>\n  <EditText android:id=\"@+id/passwordInput\" android:inputType=\"textPassword\" .../>\n  <Button android:id=\"@+id/loginButton\" android:text=\"Masuk\" .../>\n</LinearLayout>",
  "design_notes": "Warna utama: #1A73E8 (Google Blue). Font: Roboto 16sp untuk body, 20sp untuk judul."
}
```

#### Aturan Ekstraksi

```
YANG DIEKSTRAK:
  - Tipe komponen (LinearLayout, ConstraintLayout, Button, EditText, RecyclerView, dll)
  - android:id untuk setiap komponen interaktif
  - Atribut krusial: inputType, text, hint, visibility, constraintStart/End
  - Warna utama dan tipografi jika terdeteksi

YANG TIDAK PERLU DIEKSTRAK:
  - Komentar internal desainer di Figma
  - Layer dekorasi/ornamen yang tidak memiliki fungsi di Android
  - Nilai dimensi absolut (gunakan dp/sp relatif)
```

---

### 2.5 Agen RAG / PDF (`src/servers/pdf_rag.py`)

**Tujuan**: Menemukan dan menyajikan pedoman coding serta standar perusahaan dari dokumen PDF internal.

#### Mekanisme Pencarian

```
Teknologi: PostgreSQL + pgvector
Embedding: sentence-transformers/all-MiniLM-L6-v2
Collection: RAG_COLLECTION_NAME (default: "company_guidelines")
Top-k: 4 dokumen terdekat per query (similarity_search k=4)
Metadata per chunk: page (nomor halaman sumber)
```

#### Topik Prioritas yang Selalu Dicari

```
1. Naming Conventions
   Query: "naming convention Android [domain fitur]"
   
2. Arsitektur Android (MVVM / Clean Architecture)
   Query: "arsitektur MVVM [fitur yang diimplementasi]"
   
3. Best Practices Keamanan
   Query: "keamanan data [jenis data yang ditangani]"
   
4. Standar Koding Lainnya
   Query: berdasarkan task dari Planner (Context Engineering)
```

#### Format Output Wajib (ComplianceAnalysis)

```json
{
  "guideline_summary": "Proyek mengikuti Clean Architecture dengan MVVM. Semua networking melalui layer Repository, tidak langsung dari ViewModel.",
  "standards_applied": [
    "MVVM Architecture Pattern (wajib untuk semua fitur baru)",
    "Repository Pattern untuk abstraksi data source",
    "Hilt Dependency Injection (mandatory sesuai guidelines hal. 12)"
  ],
  "naming_conventions": [
    "ViewModel: NamaFiturViewModel.kt (contoh: AuthViewModel, HomeViewModel)",
    "Repository: NamaFiturRepository.kt",
    "UseCase: VerbaNamaUseCase.kt (contoh: LoginUseCase, FetchUserUseCase)",
    "Composable: PascalCase tanpa suffix (contoh: LoginScreen, UserCard)"
  ],
  "relevant_sections": [
    "Halaman 8-10: Android Architecture Guidelines",
    "Halaman 12: Dependency Injection Standards",
    "Halaman 15: Security Best Practices"
  ],
  "recommendations": "Gunakan EncryptedSharedPreferences untuk token storage. Jangan simpan credentials di plain SharedPreferences."
}
```

#### Aturan Ekstraksi

```
YANG DIEKSTRAK:
  - Standar dan pedoman yang disebutkan secara eksplisit di dokumen
  - Nomor halaman sumber (dari metadata chunk)
  - Naming conventions yang bersifat mandatori
  
YANG TIDAK BOLEH DILAKUKAN:
  - Mengarang standar yang tidak ada di dokumen
  - Menyarankan library tertentu tanpa referensi dokumen
  - Menggeneralisasi tanpa menyebut sumber halaman
  
JIKA TIDAK DITEMUKAN:
  → Katakan eksplisit: "Standar spesifik untuk [topik] tidak ditemukan di dokumen perusahaan."
  → Jangan mengarang pedoman generik sebagai pengganti
```

---

## Bagian 3 — Standar Format Intermediary (Antar Node)

Data yang mengalir **antar node** di LangGraph mengikuti format berikut:

### 3.1 Format requirement (GitLab → Orchestrator)

```json
{
  "role": "mobile developer",
  "goal": "implement JWT-based authentication",
  "benefit": "ensure secure user session management",
  "story": "As a mobile developer, I want to implement JWT-based authentication, so that I can ensure secure user session management."
}
```

> Dikirim sebagai **JSON string** (`model_dump_json(indent=2)`) ke field `requirement` di `OrchestratorState`.

### 3.2 Format SpecialistTask (Planner → Executor)

```json
{
  "task": "Cari pedoman naming convention untuk ViewModel dan Repository pattern terkait fitur autentikasi JWT.",
  "focus_areas": [
    "naming convention untuk ViewModel",
    "Repository pattern guidelines",
    "security best practices untuk token storage"
  ],
  "context_scope": "Fitur autentikasi JWT untuk mobile developer",
  "expected_output": "Daftar standar naming convention dan arsitektur yang harus diikuti untuk implementasi JWT auth"
}
```

> **Prinsip Context Engineering**: `task` BUKAN copy-paste dari user story. Ia adalah instruksi
> yang sudah difilter dan difokuskan khusus untuk domain agen tersebut.

### 3.3 Format OrchestratorState (State LangGraph)

```python
{
    "requirement":        str,           # JSON string dari GitLabAnalysis
    "agent_plan":         Dict[str, dict], # {agent_name: SpecialistTask.model_dump()}
    "code_structure":     Optional[str], # Output AndroidArchitectureAnalysis (JSON string)
    "api_contracts":      Optional[str], # Output PostmanAPIAnalysis (JSON string)
    "design_context":     Optional[str], # Output FigmaDesignAnalysis (JSON string)
    "company_guidelines": Optional[str], # Output ComplianceAnalysis (JSON string)
    "errors":             List[str],     # Akumulasi error (reducer: operator.add)
    "consolidated_output": Optional[str] # Output Markdown akhir
}
```

---

## Bagian 4 — Standar Penanganan Error

Setiap agen **wajib** menangani error tanpa menghentikan pipeline (kecuali GitLab):

```
GITLAB AGENT:
  → ValueError boleh di-raise (pipeline berhenti di integration.py Step 1)
  → Digunakan untuk: uncertainty tinggi, issue tidak ditemukan, auth gagal

SEMUA AGEN LAIN (Postman, Android, Figma, RAG):
  → DILARANG raise Exception ke luar node
  → Jika gagal: kembalikan pesan error sebagai string ke field output-nya
  → Field errors[] di OrchestratorState digunakan untuk logging, bukan penghentian
  
CONTOH PENANGANAN BENAR:
  return {"company_guidelines": f"RAG tidak tersedia: {RAG_ERROR_DETAIL}",
          "errors": ["RAG agent error: connection refused"]}

CONTOH PENANGANAN SALAH ❌:
  raise Exception("RAG gagal")  ← Ini akan menghentikan seluruh graph
```

---

## Bagian 5 — Checklist Validasi Sebelum Deploy Agen Baru

Gunakan checklist ini setiap kali menambahkan agen spesialis baru ke sistem:

```
SCHEMA:
  [ ] Model Pydantic output dibuat di src/models/schemas.py
  [ ] Model memiliki ConfigDict(extra="forbid") jika menggunakan Structured Outputs
  [ ] Semua field description ditulis dalam Bahasa Indonesia

ORCHESTRATOR:
  [ ] Optional[SpecialistTask] field ditambahkan ke PlannerDecision di schemas.py
  [ ] Node function dibuat di orchestrator.py (async def <name>_node)
  [ ] graph.add_node("<name>_node", <name>_node) ditambahkan
  [ ] graph.add_edge("<name>_node", "consolidation_node") ditambahkan
  [ ] route_to_specialists path_map diperbarui
  [ ] SUPERVISOR_PROMPT diperbarui dengan deskripsi agen baru
  [ ] ACTIVE_AGENTS list diperbarui
  [ ] consolidation_node diperbarui untuk menyertakan output agen baru

MCP CONFIG (jika via subprocess):
  [ ] MCP_SERVERS_CONFIG entry ditambahkan di orchestrator.py
  [ ] Env var yang dibutuhkan didokumentasikan di .env dan AGENTS.md

WORKSPACE DOCS:
  [ ] Tabel routing di workspace/CONTEXT.MD diperbarui
  [ ] Tabel status agen di workspace/CONTEXT.MD diperbarui
  [ ] Tabel ini (technical_blueprint.md) diperbarui dengan standar ekstraksi agen baru

TESTING:
  [ ] health_check_all_servers() diverifikasi menunjukkan agen baru ONLINE
  [ ] Setidaknya satu end-to-end run berhasil dengan agen baru aktif
```

---

## Bagian 6 — Referensi Cepat Nama Agen & Fungsi Utama

| Agen | Nama MCP/FastMCP | Fungsi Masuk | Output Schema |
|---|---|---|---|
| GitLab | — (standalone) | `run_gitlab_analyst_agent(project_id, issue_iid)` | `GitLabAnalysis` |
| Postman | `PostmanContextAgent` | `run_postman_analyst_agent(user_query)` | `PostmanAPIAnalysis` |
| Android Studio | `AndroidContextAgent` | `run_android_architect_agent(user_query)` | `AndroidArchitectureAnalysis` |
| Figma | `FigmaContextAgent` | `run_figma_analyst_agent(user_query)` | `FigmaDesignAnalysis` |
| RAG | — (direct import) | `run_compliance_expert_agent(user_query)` | `ComplianceAnalysis` |
| Orchestrator | `IntegrationOrchestrator` | `get_complete_integration_context(requirement)` | `str` (Markdown) |
