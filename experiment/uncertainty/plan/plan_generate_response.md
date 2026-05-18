# Instruksi Pembuatan Skrip Otomatisasi Generasi "User Story" untuk Pengujian Uncertainty (Skripsi)

## 1. Konteks Sistem dan Tujuan

Saya sedang mengerjakan skripsi mengenai *Uncertainty Quantification* pada sistem Multi-Agent menggunakan pendekatan *Normalized Shannon Entropy* (Semantic Clustering). 

Saya membutuhkan sebuah *script* (misalnya menggunakan Python) untuk mengotomatisasi pemanggilan **GitLab Agent**. 
* **Peran GitLab Agent:** Bertindak sebagai "The Analyst" yang menerima deskripsi *issue*, label, dan komentar, lalu mengubahnya menjadi dokumen kebutuhan fitur (Requirement Specs) berupa *User Story*.
* **Tujuan Skrip:** Skrip ini bertugas membaca 3 file dataset uji berformat JSON, mem-*parsing* setiap *issue* di dalamnya, dan menyuruh GitLab Agent men-*generate* tepat **5 sampel respons (M=5)** untuk setiap *issue*. 
* Hasil *generate* (5 sampel tersebut) harus disimpan kembali ke dalam file JSON baru sebagai *checkpoint* sebelum nantinya saya proses menggunakan Vector DB.

## 2. Struktur Data Uji (Input)

Skrip harus mampu membaca 3 file input berikut:
1. `clear_data.json` (Kelompok 1: Clear Contextual / Data Kontrol)
2. `aleatoric_data.json` (Kelompok 2: Aleatoric Uncertainty / Data Ambigu)
3. `epistemic_data.json` (Kelompok 3: Epistemic Uncertainty / Data Out-of-Domain)

**Struktur JSON Input (Contoh untuk 1 issue):**

```json
[
  {
    "id_data": "01",
    "issue_title": "[FEAT] Tambahkan filter pencarian",
    "issue_description": "Buat filter pencarian di halaman utama.",
    "issue_comments": [
      "Developer A: Filternya berdasarkan harga dan merek saja ya.",
      "Developer B: Kata manajer kemarin filternya berdasarkan kategori ketersediaan stok, bukan merek."
    ]
  }
]
```

## 3. Struktur Data Hasil (Output)

Untuk setiap file input yang diproses, skrip harus menghasilkan file output baru yang memisahkan hasil generate, misalnya:
* `responses_clear_data.json`
* `responses_aleatoric_data.json`
* `responses_epistemic_data.json`

**Struktur JSON Output yang Diharapkan:**

```json
[
  {
    "id_user_story": "US001",
    "uncertainty_type": "Clear Contextual",
    "original_issue_title": "[FEAT] Implementasi fitur autentikasi pengguna",
    "sampled_responses": [
      "User Story versi 1 dari LLM...",
      "User Story versi 2 dari LLM...",
      "User Story versi 3 dari LLM...",
      "User Story versi 4 dari LLM...",
      "User Story versi 5 dari LLM..."
    ]
  }
]
```

## 4. Alur Logika Skrip (Code Logic / Pseudocode)

Tolong buatkan kode dengan alur logika berikut:
1. **Inisialisasi Konfigurasi:** Siapkan koneksi ke LLM framework (misal: LangChain atau API LLM langsung) yang bertindak sebagai GitLab Agent dengan temperature yang diatur cukup tinggi, misal: `temperature=1.0` agar LLM bisa menghasilkan variasi sampel untuk pengujian ketidakpastian.
2. **Looping File:** Lakukan iterasi untuk memproses ketiga array nama file input tersebut secara bergantian.
3. **Looping Data Issue:** Di dalam setiap file, lakukan looping untuk setiap issue (terdapat 30 issue per file).
4. **Multiple Sampling (M=5):** Untuk setiap issue, gabungkan `issue_title`, `issue_description`, dan `issue_comments` menjadi satu teks Prompt. Lalu panggil GitLab Agent pada `src/agents/gitlab.py` sebanyak 5 kali untuk mendapatkan 5 string User Story yang berbeda.
5. **Simpan ke Output:** Masukkan kelima string tersebut ke dalam struktur array `sampled_responses` dan simpan ke file output JSON secara berkala (checkpointing) untuk mencegah kehilangan data jika terjadi putus koneksi API di tengah jalan.
6. **Error Handling:** Tambahkan blok try-except (atau catch) saat memanggil API. Jika gagal/timeout, skrip harus melakukan retry setelah delay beberapa detik.

## 5. Instruksi Format Kode
* Silakan tulis kode dalam bahasa Python (menggunakan model atau framework yang didukung project ini).
* Gunakan pustaka standar `json` dan pustaka panggilan LLM (seperti `openai` atau `langchain`).
* Berikan komentar (dalam Bahasa Indonesia) di setiap fungsi utama agar saya mudah memodifikasinya dan menjelaskannya di laporan skripsi saya.
