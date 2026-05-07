- Menguji Hyperparameter : Mengunci Temperature ke 0 untuk semua agen ekstraksi (1-5).
Langkah Langkah
1. Persiapan Dataset dan Ground Truth
Test Cases: Kumpulkan 30–50 sampel data dari GitLab (misalnya, satu paket berisi: Judul Issue, Deskripsi, Label asli, dan 5 komentar teratas).
Ground Truth (Anotasi Manual): Untuk setiap sampel, Anda (sebagai pakar/manusia) harus membuat "jawaban ideal" secara manual.  
	Tugas Klasifikasi: Tentukan apakah issue ini termasuk Feature, Bug, atau Refactor.
	Tugas Ekstraksi: Tuliskan daftar kebutuhan fungsional (functional requirements) yang benar-benar ada di dalam teks tersebut secara bersih.

2. Desain Variabel Eksperimen
Variabel Independen (Suhu): Uji sembilan titik suhu: 0.00, 0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, dan 2.00.  
Kontrol: Pastikan sistem prompt tetap sama untuk setiap pengujian agar perubahan hasil hanya dipicu oleh suhu. Gunakan juga max_tokens untuk membatasi halusinasi panjang pada suhu tinggi.

3. Prosedur Eksekusi
Sama seperti simulasi dalam paper, jalankan otomatisasi di mana setiap sampel input dikirim ke LLM sebanyak sembilan kali (sekali untuk setiap tingkat suhu).
Catatan Penting: Karena LLM bersifat probabilistik, pada suhu tinggi (di atas 1.00), jawaban model bisa berubah-ubah meskipun inputnya sama. Anda mungkin perlu menjalankan setiap sampel 3 kali per suhu untuk melihat variansnya.

4. Metode Evaluasi (Metrik)
Di dalam jurnal mengenai dampak suhu pada ekstraksi informasi uji klinis, perhitungan metrik dievaluasi dengan membandingkan keluaran model terhadap data kebenaran dasar (ground truth) yang dianotasi oleh manusia. Perhitungan ini dibagi menjadi dua berdasarkan jenis tugasnya:
a. Metrik untuk Tugas Ekstraksi Numerik (Jumlah Partisipan) Pada tugas ini, LLM diminta untuk mengekstrak jumlah partisipan dari abstrak penelitian menjadi sebuah angka tunggal
. Metrik yang digunakan meliputi: Persentase Prediksi dengan Format yang Benar: Metrik ini mengukur seberapa sering model berhasil memberikan jawaban numerik dengan format yang tepat. Jawaban diukur dengan mengonversi respons mentah model menjadi integer (bilangan bulat)
. Jika gagal (misalnya karena model mengeluarkan teks halusinasi yang tidak bisa dijadikan angka), maka format dianggap salah
. Mean Absolute Percentage Error (MAPE): Mengukur rata-rata persentase kesalahan absolut antara angka yang diprediksi oleh model dengan angka sebenarnya (ground truth)
. Proporsi Prediksi dalam Batas Kesalahan: Peneliti menghitung persentase prediksi LLM yang nilainya berdekatan dengan nilai sebenarnya, secara spesifik yang berada dalam rentang toleransi 10% dan 1% dari ground truth
2. Metrik Klasifikasi (Recall, Precision, Accuracy, F1 Score) untuk Kelengkapan Fitur Karena Requirement Specs berisi paragraf panjang yang maknanya tidak bisa diukur dengan Jaccard, Anda bisa merombak cara evaluasinya agar mirip dengan Tugas Klasifikasi di dalam jurnal
. Cara penyajian ke dosen: Ubah Ground Truth (dokumen kebutuhan) Anda menjadi sebuah checklist fitur (misalnya: 1. Ada fitur Brand filter, 2. Ada tombol Login, dsb). Kemudian, Anda baca output dari model dan berikan nilai Boolean (True/False) apakah fitur tersebut berhasil ditangkap oleh agen, terlepas dari perbedaan sinonim kata yang digunakan.
Setelah menjadi data True/False, Anda bisa menyajikan metrik statistik baku seperti Akurasi (Accuracy), Presisi (Precision), Recall, dan Skor F1 (F1 score) persis seperti yang disajikan oleh peneliti pada Tabel 2 dan Tabel 3 di dalam jurnal tersebut
. Recall akan sangat berguna untuk menunjukkan kepada dosen "berapa persen kebutuhan fitur dari issue asli yang berhasil diekstrak dan tidak terlewat oleh agen"

Gunakan pembagian metrik yang digunakan dalam paper untuk mengukur kualitas "Requirement Specs"
Integritas Format, Metrik yang digunakan (Correctly Formatted). Apakah output selalu berupa dokumen Markdown yang rapi? Paper mencatat penurunan tajam di suhu > 1.50.
Klasifikasi Label, $F1 Score$, Precision, Recall. Seberapa akurat agen menebak kategori issue (Bug/Feature) dibandingkan ground truth Anda.
Kualitas Ekstraksi, Semantic Similarity (ROUGE/BERTScore). Meskipun paper menggunakan MAPE untuk angka, untuk teks Anda bisa mengukur seberapa mirip "Requirement Specs" buatan AI dengan ground truth Anda.

Variasi Data: Untuk skripsi yang kuat, sebaiknya dataset Anda (30–50 test cases) mencakup:
30% Data Ideal: Mengikuti best practice (deskripsi jelas, label lengkap).
40% Data Standar: Penulisan rata-rata (ada typo, bahasa campuran/Indoglish).
30% Data Kompleks: Deskripsi sangat panjang, komentar yang saling bertentangan, atau informasi yang implisit.