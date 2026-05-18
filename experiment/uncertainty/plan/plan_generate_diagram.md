# Instruksi Pembuatan Skrip Visualisasi Distribusi Uncertainty Score (Jupyter Notebook)

## 1. Konteks Sistem dan Tujuan

Saya sedang mengerjakan tahap akhir eksperimen skripsi mengenai *Uncertainty Quantification* pada sistem Multi-Agent. Pada tahap sebelumnya, sistem telah berhasil menghitung nilai *Discrete Semantic Entropy* dan *Normalized Shannon Entropy* untuk 3 kelompok data uji yang berbeda.

Tujuan dari tugas ini adalah membuat sebuah skrip Python untuk **Jupyter Notebook (.ipynb)** yang memvisualisasikan grafik sebaran (distribusi histogram/KDE) dari ketiga kelompok data tersebut ke dalam satu kanvas gambar yang sama. Tujuan visualisasi ini adalah untuk melihat secara empiris titik ekuilibrium (Threshold) di mana data yang *Clear* terpisah dari data yang ambigu (*Aleatoric* & *Epistemic*).

## 2. Struktur File dan Data Uji (Input)

Terdapat 3 file JSON yang berlokasi di dalam folder `experiment/uncertainty/result/`:
1. `scored_responses_clear_data.json` (Kelompok Kontrol / Jelas)
2. `scored_responses_aleatoric_data.json` (Kelompok Ambiguitas Bahasa)
3. `scored_responses_epistemic_data.json` (Kelompok Keterbatasan Pengetahuan LLM)

**Struktur isi dari masing-masing file JSON:**

```json
[
  {
    "id_test_case": "TC_01",
    "uncertainty_type": "Aleatoric Uncertainty",
    "original_issue_title": "...",
    "discrete_semantic_entropy": 1.054,
    "normalized_uncertainty_score": 0.655
  }
]
```

## 3. Kebutuhan Visualisasi Grafik (Plotting)

Tolong buatkan kode Python untuk Jupyter Notebook dengan spesifikasi visualisasi berikut:
* **Target Metrik:** Ekstrak atribut `normalized_uncertainty_score` dari masing-masing JSON. Rentang nilainya adalah absolut dari 0.0 hingga 1.0.
* **Library:** Gunakan `pandas` untuk memanipulasi data, serta `matplotlib.pyplot` dan `seaborn` (`sns.histplot` atau `sns.kdeplot`) untuk menggambar grafik.
* **Desain Grafik:** Plot ketiga distribusi data tersebut ke dalam satu grafik yang sama menggunakan diagram histogram dengan terdapat jumlah data dari masing masing batang histogram.
* **Sumbu X:** Uncertainty Score (dengan batas 0.0 sampai 1.0).
* **Sumbu Y:** Question Frequency / Jumlah Data.
* **Pewarnaan (Sesuai Konsep):**
  * Clear Data gunakan warna Hijau (*Green*).
  * Aleatoric Data gunakan warna Merah/Oranye (*Red/Orange*).
  * Epistemic Data gunakan warna Biru (*Blue*).

## 4. Alur Logika Skrip (Code Logic)

Buatkan kode dalam satu sel Jupyter Notebook dengan alur:
1. *Import* library yang dibutuhkan.
2. Definisikan path ke 3 file JSON tersebut.
3. Buat fungsi untuk membaca JSON dan mengekstrak list dari `normalized_uncertainty_score`.
4. Masukkan data ke dalam *Pandas DataFrame* dengan kolom `score` dan `type` (Clear/Aleatoric/Epistemic).
5. Lakukan visualisasi menggunakan seaborn dan berikan penyesuaian estetika (judul, label sumbu, legend, threshold span).
6. Tampilkan plot (`plt.show()`).

## 5. Instruksi Format Output

* Buatkan kode *full* Python langsung ke dalam satu sel `.py` pada folder D:\RAG\Membuat MCP Server\experiment\uncertainty
* Pastikan penanganan file path menggunakan format relatif agar mudah disesuaikan (misal: `os.path.join`).
* Berikan komentar pada kode (dalam Bahasa Indonesia) untuk setiap tahapan.

---