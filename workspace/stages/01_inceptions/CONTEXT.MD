# CONTEXT.MD — Stage: Inception (ICM Layer 2)

> **Interpretable Context Methodology (ICM) — Layer 2: Stage Context**
> File ini adalah **kontrak tugas** untuk fase **Inception** sistem ini.
> Ia menjawab tiga pertanyaan bagi agen AI (khususnya Orchestrator Agent):
>
> 1. **Apa yang harus dibaca?** → Sumber daya dan file konteks yang relevan
> 2. **Apa yang harus dilakukan?** → Kontrak tugas tahap demi tahap
> 3. **Di mana meletakkan hasil?** → Lokasi output yang disepakati

---

## 1. Definisi Fase Ini

**Nama Tahap**: Inception
**Tujuan**: Mengekstrak, memvalidasi, dan mengstrukturkan kebutuhan pengguna dari GitLab Issue menjadi `GitLabAnalysis` — sebuah User Story terstruktur yang siap dikonsumsi oleh Orchestrator.

**Posisi dalam alur sistem**:

```
[Inception] → [Orchestration] → [Output]
     ↑
  Anda di sini
```

Fase Inception adalah **pintu masuk** sistem. Tidak ada tahap selanjutnya yang bisa berjalan tanpa output fase ini.

---

## 2. Apa yang Harus Dibaca Sebelum Mulai

Bacalah file-file berikut **secara berurutan** sebelum mengerjakan tugas apapun di fase ini:

| Prioritas | File | Alasan dibaca |
|---|---|---|
| 🔴 Wajib | [`workspace/CLAUDE.md`](../../CLAUDE.md) | Identitas sistem, arsitektur global, konvensi koding |
| 🔴 Wajib | [`workspace/CONTEXT.MD`](../../CONTEXT.MD) | Layer 1: Task routing keseluruhan workspace |
| 🔴 Wajib | [`src/models/schemas.py`](../../../src/models/schemas.py) | `GitLabAnalysis` — schema output fase ini |
| 🔴 Wajib | [`src/agents/gitlab.py`](../../../src/agents/gitlab.py) | Implementasi agen GitLab (entry point fase ini) |
| 🟡 Penting | [`src/utils/llm_factory.py`](../../../src/utils/llm_factory.py) | `create_agent_with_memory`, `execute_agent_and_structure` |
| 🟡 Penting | [`src/config/settings.py`](../../../src/config/settings.py) | `settings.gitlab_token`, `settings.gitlab_url` |
| 🟡 Penting | [`experiment/uncertainty/semantic_clustering.py`](../../../experiment/uncertainty/semantic_clustering.py) | Digunakan untuk uncertainty scoring di Fase 1 |
| 🟢 Opsional | [`AGENTS.md`](../../../AGENTS.md) | Perintah siap pakai & known gotchas |

---

## 3. Kontrak Tugas — Apa yang Harus Dilakukan

### 3.1 Entry Point

```python
# Cara memanggil agen GitLab:
from src.agents.gitlab import run_gitlab_analyst_agent

result: GitLabAnalysis = run_gitlab_analyst_agent(
    project_id="81209841",   # ID project GitLab
    issue_iid=1              # Internal ID issue
)
```

Atau lewat CLI:
```bash
uv run python -m src.integration [PROJECT_ID] [ISSUE_IID]
```

---

### 3.2 Alur Internal Fase Inception

Agen GitLab bekerja dalam **dua fase bertingkat** sebelum menghasilkan output:

```
┌────────────────────────────────────────────────────────────────────┐
│  PRE-FETCH                                                         │
│  _extract_gitlab_issue_specs_impl(project_id, issue_iid)          │
│  → Ambil: title, state, labels, description, comments dari API    │
│  → Output: issue_context (string mentah)                          │
└────────────────────────────┬───────────────────────────────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  FASE 1: UNCERTAINTY         │
              │  SAMPLING (M=5, temp=1.0)    │
              │  LLM dijalankan 5× dengan    │
              │  prompt SYSTEM_PROMPT_SAMPLING│
              │  → 5 sampel User Story       │
              └──────────────┬───────────────┘
                             │
              ┌──────────────▼──────────────┐
              │  SEMANTIC CLUSTERING         │
              │  threshold cosine = 0.90     │
              │  Hitung entropy & normalized │
              │  uncertainty score           │
              └──────────────┬───────────────┘
                             │
            ┌────────────────┴─────────────────┐
            │                                  │
   score ≤ 0.400                         score > 0.400
   (CONFIDENT)                           (UNCERTAIN)
            │                                  │
            ▼                                  ▼
  FASE 2: Eksekusi                  POST komentar eskalasi
  Deterministik (temp=0.0)          ke GitLab Issue, lalu
  SYSTEM_PROMPT_GITLAB              raise ValueError
  → GitLabAnalysis (Pydantic)       (hentikan pipeline)
```

---

### 3.3 Skema Output yang Dihasilkan

Output fase ini adalah objek `GitLabAnalysis` dari `src/models/schemas.py`:

```python
class GitLabAnalysis(BaseModel):
    role: str     # Aktor utama. Selalu "mobile developer" untuk sistem ini.
    goal: str     # Apa yang ingin dicapai. Dimulai dengan kata kerja aktif.
    benefit: str  # Nilai/manfaat yang didapat dari fitur tersebut.
    story: str    # User story lengkap: "As a [role], I want [goal], so that [benefit]."
```

> **Penting**: `GitLabAnalysis` **bukan** model OpenAI Structured Outputs (tidak ada `ConfigDict(extra="forbid")`).
> Ia dikonversi ke JSON string dengan `.model_dump_json(indent=2)` sebelum diteruskan ke Orchestrator.

---

### 3.4 Aturan yang Wajib Dipatuhi

| Aturan | Detail |
|---|---|
| **Satu aktor, satu tujuan** | User story HANYA berisi satu role dan satu goal. Jangan gabungkan kebutuhan. |
| **Role = "mobile developer"** | Format baku sistem ini. Tidak boleh diubah tanpa persetujuan. |
| **Berbasis fakta** | Jangan menebak nama class, direktori, atau teknologi jika tidak disebutkan eksplisit di issue. |
| **Threshold uncertainty = 0.400** | Jika normalized entropy > 0.400 → eskalasi ke GitLab & hentikan pipeline. |
| **Mock tool digunakan** | `extract_gitlab_issue_specs` di-mock setelah pre-fetch untuk mencegah API call berulang (rate limit). |
| **Sampling M = 5** | Selalu 5 sampel. Ubah hanya jika ada alasan eksplisit (misal: rate limit LLM). |
| **Cosine threshold = 0.90** | Untuk semantic clustering. Turunkan jika cluster terlalu banyak (false uncertainty). |

---

### 3.5 Penanganan Kondisi Error

| Kondisi | Penanganan |
|---|---|
| `GITLAB_TOKEN` tidak ada | `ValueError` langsung di `_get_gitlab_client()` |
| Issue / project tidak ditemukan | Return string error dari `_extract_gitlab_issue_specs_impl()` |
| Sampel < 2 (LLM gagal) | `normalized_score = 0.0`, lanjut ke Fase 2 tanpa uncertainty check |
| `normalized_score > 0.400` | Post komentar eskalasi → `raise ValueError` → pipeline berhenti di `integration.py` Step 1 |
| LLM Fase 2 gagal | Exception merambat ke `integration.py` dan pipeline berhenti |

---

## 4. Di Mana Meletakkan Hasil

| Hasil | Lokasi | Format |
|---|---|---|
| **Output terstruktur** | Dikembalikan sebagai `GitLabAnalysis` (return value) | Objek Pydantic |
| **JSON string untuk Orchestrator** | Di-serialize dengan `.model_dump_json(indent=2)` | JSON string → field `requirement` di `OrchestratorState` |
| **Log proses** | `stderr` (via `logging`) | Tidak disimpan ke file |
| **Komentar eskalasi** | GitLab Issue (via API `issue.notes.create()`) | Markdown comment di GitLab |
| **File output akhir (ICM)** | `workspace/stages/01_inceptions/output/technical_blueprint.md` | Dihasilkan di akhir Step 3 oleh `integration.py` sebagai *edit surface* |
| **Copy output (Global Legacy)** | `outputs/technical_context_issue_<N>.md` | Salinan global untuk kemudahan akses |

> **Catatan**: Secara ICM, output utama fase ini diletakkan di subfolder `output/` dari *stage* bersangkutan (`technical_blueprint.md`). Developer dapat langsung mengedit file ini sebagai *edit surface* sebelum lanjut ke *stage* berikutnya.

---

## 5. Kondisi Berhasil (Definition of Done)

Fase Inception dianggap **selesai dengan sukses** jika:

- [x] `run_gitlab_analyst_agent()` mengembalikan objek `GitLabAnalysis` yang valid (tidak `None`, tidak raise exception).
- [x] `story` dalam `GitLabAnalysis` mengikuti format baku: `"As a mobile developer, I want [goal], so that [benefit]."`.
- [x] `normalized_score ≤ 0.400` (sistem yakin dengan interpretasi issue).
- [x] Objek berhasil di-serialize ke JSON string dan diteruskan ke Orchestrator di Step 2.

Fase Inception dianggap **gagal** jika:

- [ ] `normalized_score > 0.400` → komentar eskalasi dikirim ke GitLab, `ValueError` di-raise.
- [ ] API GitLab tidak dapat dijangkau → exception di `_get_gitlab_client()`.
- [ ] Semua 5 sampel LLM gagal → `samples` kosong → uncertainty check dilewati tapi kualitas output tidak terjamin.

---

## 6. Cara Menambah atau Memodifikasi Fase Ini

Jika perlu mengubah perilaku fase Inception, berikut panduan perubahannya:

| Yang ingin diubah | File yang dimodifikasi |
|---|---|
| Format User Story | `SYSTEM_PROMPT_GITLAB` di `src/agents/gitlab.py` |
| Jumlah sampel uncertainty (M) | Loop `range(5)` di `run_gitlab_analyst_agent()` |
| Threshold uncertainty | Konstanta `THRESHOLD = 0.400` di `run_gitlab_analyst_agent()` |
| Cosine similarity clustering | Parameter `threshold=0.90` di panggilan `semantic_clustering()` |
| Skema output (tambah field) | `GitLabAnalysis` di `src/models/schemas.py` |
| Pesan eskalasi ke GitLab | Variable `escalation_msg` di `run_gitlab_analyst_agent()` |
| Model LLM yang digunakan | `MODEL_NAME` di `.env` atau langsung di `create_llm(temperature=...)` |

> **Setelah mengubah skema `GitLabAnalysis`**, pastikan juga memperbarui bagian
> **Step 1** di `src/integration.py` yang mengonsumsi `requirement_obj.model_dump_json()`.

---

## 7. Referensi Cepat (Quick Reference)

```bash
# Jalankan fase Inception saja (via integration, issue default)
uv run python -m src.integration

# Jalankan dengan project dan issue tertentu
uv run python -m src.integration 81209841 3

# Lihat log detail uncertainty scoring
# → Cari output "UNCERTAINTY PRE-CHECK REPORT" di terminal

# Pastikan env var tersedia
# .env harus berisi: GITLAB_TOKEN, GITLAB_URL, OPENROUTER_API_KEY
```

**Uncertainty Score Interpretation:**

| Score | Status | Tindakan |
| `0.000 – 0.400` | Yakin | Pipeline lanjut normal |
| `0.401 – 0.700` | Tidak Yakin | Eskalasi ke GitLab, pipeline berhenti |

---

## 8. Supervisor Prompt Template (Instruksi Penyusunan Unified Technical Blueprint)

Anda adalah Planner untuk sistem Android Development Automation.

Tugas Anda: Menganalisis requirement/user story, melakukan dekomposisi tugas (task decomposition),
dan membuat PLAN yang UNIK dan TERFOKUS untuk setiap agen spesialis yang relevan.

### PRINSIP CONTEXT ENGINEERING

1. PRINSIP KONTEKS MINIMUM: Setiap agen HANYA menerima konteks yang relevan dengan domainnya.
   JANGAN meneruskan seluruh User Story secara mentah ke setiap agen.

2. DEKOMPOSISI FOKUS: Pecah requirement menjadi sub-tugas yang spesifik per domain.
   Setiap sub-tugas harus jelas: apa yang harus dikerjakan, area fokus, dan output yang diharapkan.

3. ISOLASI KONTEKS: Agen A tidak perlu tahu tentang hal yang hanya relevan untuk Agen B.
   Misalnya, agen Postman tidak perlu tahu tentang pedoman coding RAG, dan sebaliknya.

4. INSTRUKSI YANG BERBEDA: Setiap agen harus menerima instruksi yang BERBEDA, bukan
   copy-paste dari user story. Sesuaikan bahasa dan detail instruksi dengan domain agen.

### Spesialis yang Tersedia

# <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
# - "android_studio": Menganalisis struktur kode proyek Android, file krusial, dan pola arsitektur.
#   Saat membuat plan untuk agen ini, fokus pada:
#   - File/modul mana yang perlu diperiksa
#   - Pola arsitektur apa yang harus ditemukan (MVVM, Clean Architecture, dll)
#   - Navigasi kode apa yang diperlukan untuk memahami implementasi fitur

# <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
# - "postman": Menganalisis API contracts dan endpoint dari koleksi Postman.
#   Saat membuat plan untuk agen ini, fokus pada:
#   - Endpoint/API mana yang relevan dengan fitur
#   - Method, request body, dan response schema apa yang dibutuhkan
#   - Alur API yang harus diikuti untuk implementasi fitur

# <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
# - "figma": Menganalisis desain UI/UX dari Figma (XML metadata).
#   Saat membuat plan untuk agen ini, fokus pada:
#   - Layar/komponen UI mana yang perlu dianalisis
#   - Elemen desain apa yang harus diekstrak (layout, style, komponen)
#   - Bagian mana dari requirement yang terkait UI/UX

- "rag": Mengambil pedoman coding dan standar perusahaan dari dokumen internal di Vector DB.
  **Koleksi**: `company_guidelines`
  **Dokumen yang tersedia**: `Suitcore Android MVVM Documentation V1`, `SuitMobile Code Style [Android] - Naming - Version 2`
  Saat membuat plan untuk agen ini:
  - WAJIB sebutkan nama dokumen spesifik yang harus dikueri
  - WAJIB sebutkan topik spesifik yang harus diekstrak (misal: "aturan penamaan ViewModel", "struktur folder MVVM")
  - JANGAN buat instruksi umum seperti "cari pedoman coding"
  - Contoh task yang BENAR: "Kueri koleksi 'company_guidelines' untuk dokumen 'Suitcore Android MVVM Documentation V1'. Ekstrak aturan struktur folder dan pola ViewModel untuk fitur autentikasi."

### Constraint

Server yang AKTIF saat ini: {active_servers}
RAG status: {rag_status}
Jika sebuah server atau RAG tidak aktif, JANGAN buat plan untuk agen tersebut.

### Requirement

{requirement}

Buat PLAN yang UNIK untuk setiap agen. Setiap plan WAJIB mengandung:
- task: Instruksi spesifik yang hanya berisi konteks relevan untuk domain agen tersebut (BUKAN copy-paste User Story!)
- focus_areas: Daftar aspek spesifik yang harus difokuskan (misal: ["naming convention untuk ViewModel", "pola Repository pattern"])
- context_scope: HANYA bagian dari requirement yang relevan untuk agen ini (bukan seluruh story)
- expected_output: Jenis output yang diharapkan dari agen ini

PENTING: Setiap agen harus menerima instruksi yang BERBEDA dan TERFOKUS pada domainnya masing-masing.
JANGAN mengulang seluruh User Story di setiap plan.
