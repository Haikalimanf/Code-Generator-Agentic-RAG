# Instruksi Pembuatan Skrip Semantic Clustering dan Perhitungan Uncertainty Score

## 1. Konteks Sistem dan Tujuan

Saya sedang melanjutkan pengerjaan skripsi mengenai *Uncertainty Quantification* pada sistem Multi-Agent. Pada tahap sebelumnya, Agen GitLab telah men-*generate* 5 sampel *User Story* ($M=5$) untuk setiap *Issue* dan menyimpannya dalam format JSON. 

Tujuan skrip yang akan dibuat ini adalah:
1. Membaca file JSON yang berisi kumpulan sampel respons tersebut.
2. Melakukan **Semantic Clustering** (pengelompokan makna semantik) pada 5 sampel respons tersebut menggunakan model *embedding* (Vector Database).
3. Menghitung nilai **Discrete Semantic Entropy**.
4. Menormalisasi nilai entropi tersebut menjadi **Normalized Shannon Entropy** (skala 0.0 hingga 1.0).
5. Menyimpan hasil perhitungannya kembali ke dalam format JSON baru untuk keperluan analisis distribusi (sebaran) data.

## 2. Acuan Modul Embedding

Di dalam struktur proyek saya, saya sudah memiliki modul untuk memproses *embedding* dokumen. Tolong gunakan modul/fungsi *embedding* yang merujuk pada file berikut sebagai acuan arsitektur *vector* Anda:
* `src/servers/pdf_rag.py`
* `src/ingest_pdf.py`

Silakan *import* atau simulasikan penggunaan fungsi *embedding* dari file-file tersebut untuk mengubah teks *User Story* menjadi vektor sebelum menghitung kemiripan (misal menggunakan *Cosine Similarity*).

## 3. Struktur Data Uji (Input)

Skrip harus mampu membaca file JSON hasil *generate* sebelumnya. Contoh struktur `responses_*.json` untuk satu *issue* adalah sebagai berikut:

```json
[
  {
    "id_test_case": "TC002_01",
    "uncertainty_type": "Aleatoric Uncertainty",
    "original_issue_title": "[FEAT] Tambahkan filter pencarian",
    "sampled_responses": [
      "Sebagai user, saya bisa memfilter produk berdasarkan brand.",
      "Sebagai pengguna, saya dapat menyaring barang sesuai merek.",
      "Sebagai admin, saya bisa mengurutkan produk dari harga termurah.",
      "User dapat melakukan filter pencarian berdasarkan harga.",
      "Sebagai sistem, filter dilakukan berdasarkan kategori stok."
    ]
  }
]
```

## 4. Struktur Data Hasil (Output)

Hasil dari proses klasterisasi dan perhitungan entropi harus disimpan dalam file JSON baru (misal: `scored_responses_*.json`). Struktur yang diharapkan:

```json
[
  {
    "id_test_case": "TC002_01",
    "uncertainty_type": "Aleatoric Uncertainty",
    "original_issue_title": "[FEAT] Tambahkan filter pencarian",
    "total_clusters": 3,
    "clusters_distribution": [
      {"cluster_id": 1, "count": 2, "probability": 0.4},
      {"cluster_id": 2, "count": 2, "probability": 0.4},
      {"cluster_id": 3, "count": 1, "probability": 0.2}
    ],
    "discrete_semantic_entropy": 1.054,
    "normalized_uncertainty_score": 0.655
  }
]
```
*(Perhatikan: Tidak perlu memberikan label status Accept/Reject, cukup keluarkan angka skor akhirnya saja).*

## 5. Alur Logika Skrip (Code Logic / Pseudocode)

Tolong buatkan kode Python dengan alur logika berikut:
1. **Looping Data JSON:** Baca array data dari file JSON input.
2. **Vector Embedding:** Ekstrak array `sampled_responses` yang berisi 5 kalimat. Misalkan jumlah total sampel adalah $M$ (di mana $M=5$). Masukkan kalimat ke dalam fungsi embedding yang mengacu pada `src/servers/pdf_rag.py` atau `src/ingest_pdf.py` untuk mendapatkan nilai vektornya.
3. **Semantic Clustering:** Hitung jarak antar vektor menggunakan *Cosine Similarity*. Kelompokkan kalimat-kalimat yang memiliki nilai kemiripan di atas *threshold embedding* tertentu (misalnya >0.85) ke dalam klaster yang sama. Misalkan jumlah total klaster yang terbentuk adalah $K$.
4. **Hitung Probabilitas Klaster:** Untuk setiap klaster ke-$k$, hitung probabilitasnya menggunakan rumus yang tertera pada referensi di bawah.
5. **Hitung Entropy:** Kalkulasikan nilai *Discrete Semantic Entropy* dan *Normalized Shannon Entropy* menggunakan rumus probabilitas yang telah didapatkan.
6. **Simpan ke JSON:** Tulis (*dump*) hasil kalkulasi atribut-atribut di atas ke file output berformat JSON.

---

## Referensi Rumus Matematika (Uncertainty Estimation LLM)

### 1. Semantic Entropy (Semantic Clustering)

Semantic Entropy digunakan untuk mengukur ketidakpastian model dengan mengelompokkan respons-respons yang memiliki makna serupa ke dalam kluster, kemudian menghitung entropy dari distribusi probabilitas antar kluster tersebut.

**Rumus Utama:**
Nilai Semantic Entropy $U$ didefinisikan sebagai:

$$
U = -\sum_{k=1}^{K} p(\mathbf{R}_k) \log p(\mathbf{R}_k)
$$

di mana probabilitas setiap kluster $p(\mathbf{R}_k)$ dihitung sebagai:

$$
p(\mathbf{R}_k) = \sum_{r_j \in \mathbf{R}_k} \exp\!\left(\frac{1}{|r_j|} \sum_{i=1}^{|r_j|} \log p_{z_i}\right)
$$

**Keterangan Variabel:**
| Simbol | Keterangan |
|---|---|
| $U$ | Nilai estimasi ketidakpastian |
| $K$ | Jumlah total kluster respons |
| $\mathbf{R}_k$ | Kluster respons ke-$k$ |
| $p(\mathbf{R}_k)$ | Probabilitas kluster ke-$k$ |
| $r_j$ | Respons ke-$j$ dalam kluster $\mathbf{R}_k$ |
| $\|r_j\|$ | Jumlah token dalam respons $r_j$ |
| $p_{z_i}$ | Probabilitas token ke-$i$ dalam respons |

### 2. Normalized Shannon Entropy

Normalized Shannon Entropy digunakan untuk mengukur ketidakpastian secara per-token, kemudian dinormalisasi agar dapat dibandingkan antar sekuens atau model yang berbeda.

**Entropy Per Posisi Token:**
Untuk setiap posisi $i$ pada sekuens output, entropy $H_i$ dihitung sebagai:

$$
H_i = -\sum_{y \in \mathcal{V}} P_i(y \mid \mathbf{x}, y_{1:i-1}) \log P_i(y \mid \mathbf{x}, y_{1:i-1})
$$

**Total Conditional Entropy:**
Total conditional entropy $H(\mathbf{y} \mid \mathbf{x})$ dari seluruh sekuens output adalah:

$$
H(\mathbf{y} \mid \mathbf{x}) = \sum_{i=1}^{n} H_i
$$

**Normalized Entropy Per Token:**
Normalized entropy $h_i$ pada posisi $i$ didefinisikan sebagai:

$$
h_i = \frac{H_i}{H_i^{\max}} = \frac{H_i}{\log |\mathcal{V}|}
$$
*(Di mana entropy maksimum $H_i^{\max} = \log |\mathcal{V}|$ terjadi saat distribusi token seragam di seluruh kosakata).*

**Normalized Total Entropy:**
Normalized entropy total $\overline{H}(\mathbf{y} \mid \mathbf{x})$ dari seluruh sekuens dihitung sebagai:

$$
\overline{H}(\mathbf{y} \mid \mathbf{x}) = \frac{H(\mathbf{y} \mid \mathbf{x})}{H^{\max}(\mathbf{y})} = \frac{\sum_{i=1}^{n} H_i}{n \log |\mathcal{V}|} = \frac{1}{n} \sum_{i=1}^{n} h_i
$$

Nilai $\overline{H}(\mathbf{y} \mid \mathbf{x})$ berkisar antara $0$ dan $1$, di mana:
- $\overline{H} = 0$ → model **sangat yakin** pada setiap prediksi token
- $\overline{H} = 1$ → model **sama sekali tidak yakin** (distribusi seragam)

**Keterangan Variabel:**
| Simbol | Keterangan |
|---|---|
| $H_i$ | Entropy pada posisi token ke-$i$ |
| $\mathcal{V}$ | Kosakata (*vocabulary*) semua token yang mungkin |
| $\|\mathcal{V}\|$ | Ukuran kosakata |
| $P_i(y \mid \mathbf{x}, y_{1:i-1})$ | Probabilitas token $y$ pada posisi ke-$i$ |
| $\mathbf{x}$ | Input (gambar + prompt) |
| $n$ | Jumlah total token output |
| $h_i$ | Normalized entropy pada posisi ke-$i$ |
| $\overline{H}(\mathbf{y} \mid \mathbf{x})$ | Normalized entropy total sekuens output |

---

## 6. Instruksi Format Kode

* Silakan tulis dalam bahasa Python.
* Asumsikan bahwa saya bisa meng-*import* *embedding retriever* atau *vector store* dari `src.servers.pdf_rag`. 
* Berikan komentar (`# TODO: Import fungsi dari src.ingest_pdf`) di bagian yang memerlukan penyesuaian import secara manual.
