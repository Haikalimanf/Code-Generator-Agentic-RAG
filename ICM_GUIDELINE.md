---

# Panduan Interpretable Context Methodology (ICM) untuk Folder `stages`

## 1. Apa itu Interpretable Context Methodology (ICM)?

ICM adalah sebuah metodologi arsitektur yang menggantikan kerangka kerja (*framework*) orkestrasi multi-agen berbasis kode yang rumit dengan struktur folder atau sistem file biasa

Alih-alih menggunakan skrip Python yang kompleks untuk mengatur kapan sebuah agen harus bekerja, ICM murni mengandalkan folder bernomor, file teks *markdown*, dan skrip lokal untuk mengatur alur kerja agen

## 2. Fungsi Utama Folder `stages/`

Folder `stages/` adalah infrastruktur utama yang mengendalikan alur kerja agen. Folder ini mendikte urutan eksekusi dan membatasi secara ketat informasi apa saja yang boleh diakses oleh agen pada suatu waktu.

Prinsip kerjanya adalah sebagai berikut:

- **Satu Tahapan, Satu Pekerjaan (*One Stage, One Job*)**
  Setiap tahap yang direpresentasikan oleh folder bernomor (contoh: `01_inception`, `02_development`) difokuskan untuk menyelesaikan satu langkah transformasi data yang spesifik secara optimal.

- **Pola Pipa Unix (*Unix Pipeline*)**
  Output dari tahap sebelumnya akan secara otomatis menjadi masukan (*input*) utama bagi tahap berikutnya

- **Pembatasan Konteks Eksekusi**
  Agen **hanya memuat (*load*) konteks yang benar-benar relevan** untuk *stage* yang sedang dikerjakannya. Hal ini dirancang untuk mencegah agen memproses puluhan ribu token yang tidak relevan yang sering menyebabkan kebingungan pada model (fenomena *"lost in the middle"*)

## 3. Anatomi di Dalam Setiap Folder Stage

Agen yang beroperasi di dalam folder `stages/` diwajibkan mematuhi hierarki konteks berlapis. Di dalam setiap folder *stage*, terdapat tiga komponen wajib:

### A. `CONTEXT.md` (Layer 2: Stage Context)

File ini adalah **"kontrak kerja"** yang bertindak sebagai titik kendali utama sistem untuk tahap tersebut. Agen wajib menjadikan file ini sebagai acuan instruksi mutlak untuk mengetahui:

- **Inputs**: Menentukan secara persis direktori atau file mana saja dari tahap sebelumnya dan referensi mana yang boleh dibaca.
- **Process**: Instruksi yang menjabarkan apa yang harus dieksekusi oleh agen pada tahap ini.
- **Outputs**: Perintah yang mewajibkan agen menyimpan hasil kerjanya pada direktori yang tepat.

### B. Folder `references/` (Layer 3: Reference Material)

Folder ini berisi panduan, templat, pedoman desain, atau konvensi (*style guide*) yang bersifat stabil dan **tidak berubah** pada setiap eksekusi *pipeline*

Agen harus memperlakukan data di dalam folder ini sebagai **batasan atau aturan kaku (*constraints*)** yang harus diinternalisasi saat agen memproses *input*

### C. Folder `output/` (Layer 4: Working Artifacts)

Folder ini adalah tempat agen memproduksi dan menaruh artefak hasil kerjanya. Berbeda dengan referensi, file di sini akan selalu diperbarui atau berubah di setiap eksekusi tugas baru 

Agen **hanya boleh** menulis (*write*) hasil akhir pada folder `output/` ini 

## 4. Mekanisme Handoff dan Intervensi Manusia (*Review Gates*)

Setiap hasil kerja antara (*intermediate output*) dari sebuah *stage* adalah sebuah file teks biasa (*markdown* atau kode) yang mudah dibaca. Arsitektur ini menjadikan setiap pergantian folder sebagai **gerbang peninjauan (*review gates*) yang transparan**

Penting bagi agen untuk berhenti bekerja setelah menulis ke folder `output/`. Output ini adalah "permukaan yang bisa diedit" (*edit surface*), yang berarti manusia (*developer*) dapat dengan mudah membuka, membaca, atau merevisi hasil sementara tersebut secara manual

Jika sudah disetujui, agen di tahap selanjutnya baru akan membaca file yang telah diedit/divalidasi tersebut sebagai masukannya.

---
