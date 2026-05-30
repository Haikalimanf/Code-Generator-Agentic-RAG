# Technical Blueprint — Inception Stage
## Pedoman Ekstraksi & Standar Format Data Antar Agen

> **Jenis Dokumen**: Factory Reference (Stabil, Tidak Berubah per Eksekusi)
> **Berlaku untuk**: Semua agen yang beroperasi di fase Inception
> **Tujuan**: Menjamin konsistensi format data yang dikirim dari setiap agen spesialis
> ke Orchestrator, sehingga `consolidation_node` dapat memproses output tanpa ambiguitas.

---

## Prinsip Dasar

Blueprint ini berlaku untuk semua agen, baik yang **aktif** maupun yang **dinonaktifkan sementara**. Ketika sebuah agen diaktifkan kembali (via `# <-- UNCOMMENT`), ia **wajib** mengikuti format yang didefinisikan di dokumen ini tanpa negosiasi.

Setiap agen menghasilkan **satu objek Pydantic** yang di-serialize ke JSON string. Objek tersebut diletakkan ke field yang sesuai dalam `OrchestratorState`. `consolidation_node` kemudian merangkainya menjadi satu dokumen Markdown akhir.

```
Agen Spesialis → Pydantic Model → JSON String → OrchestratorState field → consolidation_node → Markdown Output
```

---

## 1. Standar Format: GitLab Agent

**Agen**: `src/agents/gitlab.py` → `run_gitlab_analyst_agent()`
**Output model**: `GitLabAnalysis` (`src/models/schemas.py`)
**Destination field**: `OrchestratorState["requirement"]` (sebagai JSON string)

### Skema Wajib

```json
{
  "role": "mobile developer",
  "goal": "<kata kerja aktif> + <objek tindakan>",
  "benefit": "<nilai bisnis atau teknis yang konkret>",
  "story": "As a mobile developer, I want <goal>, so that <benefit>."
}
```

### Aturan Ekstraksi

| Field | Aturan |
|---|---|
| `role` | **Selalu** `"mobile developer"`. Tidak ada variasi lain yang diizinkan. |
| `goal` | Dimulai dengan **kata kerja aktif** (implement, integrate, create, display, manage). Hindari kata kerja pasif (dibuat, dilakukan). |
| `benefit` | Jelaskan **dampak konkret** bagi developer atau end-user. Hindari jawaban abstrak seperti "agar lebih baik". |
| `story` | Ikuti format baku persis: `"As a [role], I want [goal], so that [benefit]."` — titik di akhir, tidak ada baris baru. |

### Aturan Kualitas

- **Satu aktor, satu tujuan**: Jangan menggabungkan beberapa kebutuhan dalam satu story.
- **Berbasis fakta**: Tidak boleh menyebutkan nama class, path file, atau teknologi spesifik kecuali disebutkan eksplisit di issue.
- **Panjang goal**: Maksimal 15 kata.
- **Panjang benefit**: Maksimal 20 kata.

### Contoh Valid

```json
{
  "role": "mobile developer",
  "goal": "integrate the OTP verification flow into the registration screen",
  "benefit": "users can securely verify their phone number during account creation",
  "story": "As a mobile developer, I want to integrate the OTP verification flow into the registration screen, so that users can securely verify their phone number during account creation."
}
```

### Contoh Tidak Valid ❌

```json
{
  "role": "user",
  "goal": "bisa login dan register dan juga lihat profil",
  "benefit": "lebih mudah",
  "story": "As a user, I want to bisa login dan register, so that lebih mudah."
}
```
*Alasan gagal: role salah, goal menggabungkan banyak kebutuhan, benefit abstrak, grammar tidak baku.*

---

## 2. Standar Format: RAG Agent (Aktif)

**Agen**: `src/servers/pdf_rag.py` → `run_compliance_expert_agent()`
**Output model**: `ComplianceAnalysis` (`src/models/schemas.py`)
**Destination field**: `OrchestratorState["company_guidelines"]` (sebagai JSON string)

### Skema Wajib

```json
{
  "guideline_summary": "<ringkasan 2–4 kalimat pedoman yang relevan>",
  "standards_applied": [
    "<standar 1: nama pola/konvensi yang wajib diikuti>",
    "<standar 2>"
  ],
  "naming_conventions": [
    "<aturan penamaan 1, contoh: ViewModel suffix wajib untuk semua ViewModel class>",
    "<aturan penamaan 2>"
  ],
  "relevant_sections": [
    "<referensi dokumen: 'Bab 3 - Android Architecture', hal. 12>",
    "<referensi lain>"
  ],
  "recommendations": "<saran konkret implementasi, atau null jika tidak ada>"
}
```

### Aturan Ekstraksi

| Field | Aturan |
|---|---|
| `guideline_summary` | Wajib diisi. Ringkasan dalam **Bahasa Indonesia**. Maksimal 4 kalimat. |
| `standards_applied` | Minimal 1 item. Format: `"<nama standar>: <deskripsi singkat>"`. |
| `naming_conventions` | Boleh kosong `[]` jika tidak ditemukan di dokumen. Jangan mengarang. |
| `relevant_sections` | Sertakan nomor halaman atau judul bab jika tersedia di metadata dokumen. |
| `recommendations` | `null` jika tidak ada saran tambahan. Jangan isi dengan placeholder. |

### Aturan Kualitas RAG

- **Hanya dari dokumen**: Jika fakta tidak ada di vectorstore, nyatakan `"Standar spesifik tidak ditemukan dalam dokumen perusahaan."` — jangan mengarang.
- **Similarity search k=4**: Maksimal 4 dokumen diambil per query (`vectorstore.similarity_search(query, k=4)`).
- **Query spesifik**: Task dari Planner harus spesifik (misal: "naming convention untuk ViewModel Android") — bukan query generik.
- **Thread ID**: Gunakan thread ID unik per eksekusi untuk mencegah kontaminasi memori antar session.

### Contoh Valid

```json
{
  "guideline_summary": "Perusahaan mewajibkan pola MVVM dengan LiveData untuk semua layar Android. Setiap ViewModel wajib menggunakan suffix 'ViewModel'. Repository harus menjadi satu-satunya sumber data (single source of truth).",
  "standards_applied": [
    "MVVM Architecture: wajib digunakan di semua modul fitur",
    "Repository Pattern: data hanya boleh diakses melalui Repository"
  ],
  "naming_conventions": [
    "ViewModel class: suffix 'ViewModel' (contoh: LoginViewModel)",
    "Repository class: suffix 'Repository' (contoh: UserRepository)",
    "LiveData variable: prefix 'ld' (contoh: ldUserData)"
  ],
  "relevant_sections": [
    "Bab 2 - Android Architecture Guidelines, hal. 7–9",
    "Appendix A - Naming Conventions, hal. 34"
  ],
  "recommendations": "Pastikan setiap ViewModel menggunakan ViewModelFactory jika membutuhkan dependency injection manual."
}
```

---

## 3. Standar Format: Postman Agent (Nonaktif — Siap Diaktifkan)

**Agen**: `src/servers/postman.py` → `run_postman_analyst_agent()`
**Output model**: `PostmanAPIAnalysis` (`src/models/schemas.py`)
**Destination field**: `OrchestratorState["api_contracts"]` (sebagai JSON string)

### Skema Wajib

```json
{
  "feature_summary": "<deskripsi fitur yang dianalisis>",
  "relevant_endpoints": [
    "POST /auth/otp/send — Mengirim OTP ke nomor telepon",
    "POST /auth/otp/verify — Memverifikasi kode OTP yang diterima"
  ],
  "api_contracts": [
    "POST /auth/otp/send\n  Request: { phone_number: string }\n  Response 200: { message: string, expires_in: int }\n  Response 400: { error: string }",
    "POST /auth/otp/verify\n  Request: { phone_number: string, otp_code: string }\n  Response 200: { token: string, user_id: string }\n  Response 401: { error: 'OTP invalid or expired' }"
  ],
  "missing_endpoints": [
    "Endpoint untuk resend OTP tidak ditemukan di collection"
  ],
  "recommendations": "Tambahkan endpoint POST /auth/otp/resend dengan rate limiting 60 detik."
}
```

### Aturan Ekstraksi

| Field | Aturan |
|---|---|
| `feature_summary` | Satu kalimat. Jelaskan fitur apa yang dianalisis dari perspektif API. |
| `relevant_endpoints` | Format: `"<METHOD> <path> — <deskripsi singkat>"`. Hanya endpoint yang benar-benar relevan. |
| `api_contracts` | Detail lengkap: HTTP method, path, request body, response sukses, response error. Gunakan format teks terstruktur. |
| `missing_endpoints` | Kosong `[]` jika semua endpoint ditemukan. Jangan mengarang endpoint yang tidak ada. |
| `recommendations` | `null` jika tidak ada rekomendasi. Berikan saran konkret jika ada gap. |

### Aturan Kualitas Postman

- **Hanya dari collection**: Tidak boleh menambahkan endpoint yang tidak ada di Postman collection atau JSON file.
- **Cache-aware**: Response Postman API di-cache 1 jam di `postman_cache/`. Hapus folder jika data stale.
- **Filter relevansi**: Hanya tampilkan endpoint yang relevan dengan task dari Planner — jangan dump seluruh collection.
- **Format endpoint**: Selalu `"<METHOD> <path>"` — uppercase untuk method, lowercase untuk path.

---

## 4. Standar Format: Android Studio Agent (Nonaktif — Siap Diaktifkan)

**Agen**: `src/servers/android_studio.py` → `run_android_architect_agent()`
**Output model**: `AndroidArchitectureAnalysis` (`src/models/schemas.py`)
**Destination field**: `OrchestratorState["code_structure"]` (sebagai JSON string)

### Skema Wajib

```json
{
  "overview": "<ringkasan struktur project: modul, bahasa, build system>",
  "key_components": [
    "LoginViewModel (ui/login/): Mengelola state dan logika autentikasi",
    "UserRepository (data/repository/): Sumber data tunggal untuk data pengguna"
  ],
  "data_flow": "<penjelasan aliran data dari UI ke data layer dan kembali ke UI>",
  "relevant_files": [
    "app/src/main/java/com/example/ui/login/LoginActivity.kt",
    "app/src/main/java/com/example/data/repository/UserRepository.kt"
  ],
  "architectural_patterns": [
    "MVVM dengan LiveData",
    "Repository Pattern",
    "Dependency Injection via Hilt"
  ],
  "recommendations": "<saran refactoring atau integrasi jika ada, atau null>"
}
```

### Aturan Ekstraksi

| Field | Aturan |
|---|---|
| `overview` | Maksimal 3 kalimat. Sebutkan modul utama, bahasa (Kotlin/Java), dan build system. |
| `key_components` | Format: `"<NamaClass> (<path relatif>/): <peran dalam arsitektur>"`. |
| `data_flow` | Jelaskan aliran data dari layer UI → ViewModel → Repository → DataSource dan balik. |
| `relevant_files` | Gunakan **path relatif dari root project Android**. Hanya file yang benar-benar relevan dengan task. |
| `architectural_patterns` | Gunakan nama pola yang diakui (MVVM, MVP, Clean Architecture, dll). Jangan menebak jika tidak terdeteksi. |
| `recommendations` | `null` jika tidak ada. Berikan rekomendasi jika ada inkonsistensi arsitektur. |

### Aturan Kualitas Android Studio

- **Hanya dari file yang ada**: Jangan menyebutkan class atau file yang tidak ditemukan di project.
- **Path relatif**: Selalu gunakan path relatif dari root project Android, bukan path absolut mesin lokal.
- **Fokus pada relevansi**: Filter hanya komponen yang terkait dengan task dari Planner — jangan analisis seluruh project.
- **ANDROID_PROJECT_ROOT**: Pastikan env var ini di-set sebelum agen diaktifkan.

---

## 5. Standar Format: Figma Agent (Nonaktif — Siap Diaktifkan)

**Agen**: `src/servers/figma.py` → agen Figma via `_call_tool("figma", "get_figma_xml_metadata", ...)`
**Output model**: `FigmaDesignAnalysis` (`src/models/schemas.py`)
**Destination field**: `OrchestratorState["design_context"]` (sebagai JSON string)

### Skema Wajib

```json
{
  "feature_name": "<nama fitur atau nama layar yang dianalisis>",
  "node_id": "<Figma node ID, format: 'XXXX:XXXX'>",
  "structure_summary": "<ringkasan struktur UI: jumlah layar, komponen utama, layout>",
  "key_components": [
    {"id": "2335:6401", "name": "OTP Input Field", "type": "INPUT"},
    {"id": "2335:6405", "name": "Verify Button", "type": "BUTTON"}
  ],
  "xml_context": "<potongan XML metadata Figma yang paling relevan>",
  "design_notes": "<catatan desain: warna, typography, spacing — atau null>"
}
```

### Aturan Ekstraksi

| Field | Aturan |
|---|---|
| `feature_name` | Nama layar dalam Figma (sesuai dengan label di design file). |
| `node_id` | Format Figma: `"XXXX:XXXX"`. Diambil dari `FIGMA_NODE_MAP` di orchestrator. |
| `structure_summary` | Maksimal 3 kalimat. Fokus pada hierarki komponen dan layout utama. |
| `key_components` | Array of object `{id, name, type}`. Hanya komponen interaktif atau struktural utama. |
| `xml_context` | Potongan XML metadata yang diambil dari Figma Desktop App. Jangan include seluruh XML — filter yang relevan. |
| `design_notes` | `null` jika tidak ada. Sertakan jika ada token desain khusus yang harus diimplementasikan. |

### Aturan Kualitas Figma

- **Figma Desktop App wajib aktif**: Agen ini bergantung pada Figma Desktop App dengan Dev Mode dan `mcp-remote` npm package.
- **FIGMA_NODE_MAP**: Node ID dipetakan dari keyword di task Planner. Periksa mapping di `orchestrator.py` sebelum mengaktifkan.
- **XML hanya potongan relevan**: Jangan mengirimkan seluruh XML tree — filter komponen yang relevan dengan task.
- **Fallback node**: Default node ID `"2335:6376"` digunakan jika keyword tidak cocok dengan FIGMA_NODE_MAP.

---

## 6. Standar Format: `SpecialistTask` (Input dari Planner ke Setiap Agen)

Setiap agen menerima input berupa `SpecialistTask` dari `PlannerDecision`. Ini adalah **kontrak input** yang wajib dipatuhi Planner saat membuat plan.

### Skema Wajib

```json
{
  "task": "<instruksi spesifik dan terfokus — BUKAN user story mentah>",
  "focus_areas": [
    "<aspek spesifik 1 yang harus difokuskan>",
    "<aspek spesifik 2>"
  ],
  "context_scope": "<hanya bagian user story yang relevan untuk agen ini>",
  "expected_output": "<jenis output yang diharapkan dari agen ini>"
}
```

### Aturan per Agen

| Agen | `task` harus berisi | `focus_areas` tipikal | `expected_output` tipikal |
|---|---|---|---|
| `rag` | Query spesifik tentang standar coding yang relevan dengan fitur | Naming conventions, arsitektur, security patterns | Analisis compliance dan rekomendasi implementasi |
| `postman` | Nama fitur + endpoint yang dicurigai relevan | Method HTTP, request/response schema, auth flow | Daftar API contract yang siap dikonsumsi developer |
| `android_studio` | Nama fitur + komponen Android yang perlu dianalisis | File/class yang relevan, pola arsitektur yang digunakan | Peta komponen dan aliran data untuk fitur tersebut |
| `figma` | Nama layar Figma + elemen desain yang dibutuhkan | Layout utama, komponen interaktif, token desain | XML metadata dan catatan implementasi UI |

### Larangan untuk Planner

- ❌ Jangan copy-paste seluruh user story ke field `task` setiap agen.
- ❌ Jangan membuat `task` untuk agen yang tidak aktif (`android_studio`, `postman`, `figma` saat masih di-comment).
- ❌ Jangan biarkan `focus_areas` kosong jika agen membutuhkan arah spesifik.

---

## 7. Standar Output Akhir: `consolidation_node`

`consolidation_node` merangkai semua output specialist menjadi satu dokumen Markdown. Struktur dokumen akhir yang dihasilkan ke `outputs/technical_context_issue_<N>.md` harus mengikuti urutan bagian berikut:

```markdown
# Technical Integration Context Blueprint

## Kebutuhan Sistem / Requirement
<Informasi dari GitLabAnalysis: role, goal, benefit, story>

**Specialist Agents Terlibat**: `rag`, `postman`, ...

### Rincian Plan Hasil Dekomposisi (Planner → Context Engineering)

#### `<nama_agen>`
- **Task**: ...
- **Focus Areas**: ...
- **Context Scope**: ...
- **Expected Output**: ...

---

## 1. Struktur & File Project (Android Studio)       ← jika aktif
## 2. API Contracts (Postman)                        ← jika aktif
## 3. Desain UI & XML (Figma)                        ← jika aktif
## Pedoman Coding & Best Practices (RAG)             ← selalu aktif

---

## Errors & Peringatan Selama Proses                 ← jika ada error
```

### Aturan Konsolidasi

- Bagian yang agennya tidak aktif **tidak boleh muncul** di output akhir.
- Jika semua agen menghasilkan error, `consolidated_output` tetap dihasilkan dengan bagian **Errors & Peringatan**.
- Format JSON dalam tiap bagian dibungkus dalam code block ` ```json ... ``` `.
- Separator antar bagian menggunakan `\n\n---\n\n` (bukan `---` saja).

---

## 8. Matriks Kompatibilitas Format

Tabel ini memastikan tidak ada ketidakcocokan tipe data antara output agen dan field `OrchestratorState`:

| Agen | Pydantic Model | Field di `OrchestratorState` | Tipe di State | Cara Serialize |
|---|---|---|---|---|
| GitLab | `GitLabAnalysis` | `requirement` | `str` | `.model_dump_json(indent=2)` |
| RAG | `ComplianceAnalysis` | `company_guidelines` | `Optional[str]` | `.model_dump_json(indent=2)` |
| Postman | `PostmanAPIAnalysis` | `api_contracts` | `Optional[str]` | `.model_dump_json(indent=2)` |
| Android Studio | `AndroidArchitectureAnalysis` | `code_structure` | `Optional[str]` | `.model_dump_json(indent=2)` |
| Figma | `FigmaDesignAnalysis` | `design_context` | `Optional[str]` | `.model_dump_json(indent=2)` |

> **Aturan**: Semua output agen harus di-serialize ke **JSON string** sebelum diletakkan ke state.
> `consolidation_node` akan menangani deserialization via `json.loads()` dan formatting.

---

## 9. Checklist Validasi Sebelum Agen Baru Diaktifkan

Gunakan checklist ini setiap kali mengaktifkan agen yang sebelumnya di-comment:

```
[ ] Skema Pydantic model di schemas.py sudah mengikuti format di dokumen ini
[ ] Field di OrchestratorState sudah di-uncomment
[ ] Node di LangGraph graph sudah di-uncomment (add_node + add_edge)
[ ] PlannerDecision di schemas.py sudah menambahkan Optional[SpecialistTask] field baru
[ ] SUPERVISOR_PROMPT di orchestrator.py sudah menyebutkan agen baru
[ ] AGENT_TO_NODE mapping sudah diperbarui
[ ] MCP_SERVERS_CONFIG entry sudah di-uncomment
[ ] Env var yang dibutuhkan sudah ada di .env
[ ] Format output agen sudah sesuai dengan bagian yang relevan di dokumen ini
[ ] consolidation_node sudah di-uncomment untuk menampilkan output agen baru
```
