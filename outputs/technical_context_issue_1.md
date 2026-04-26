# Technical Context for Issue #1

Berikut adalah laporan teknis komprehensif berdasarkan requirement sistem autentikasi pengguna yang Anda berikan, dengan hasil pencarian dari berbagai sumber teknis (Android Studio, Postman, Figma, dan pedoman perusahaan):

---

## 1. Struktur Project & File Terkait (Android Studio)

### Struktur Proyek
- **Modul utama:** `app`
- **Folder penting:**
  - `app/src/main/java/com/mp/basemvvm/ui/login/` (Login)
  - `app/src/main/java/com/mp/basemvvm/ui/register/` (Register)
  - `app/src/main/res/layout/` (Layout XML)
  - `app/src/main/AndroidManifest.xml` (Manifest)
- **Firebase:** Ada integrasi Firebase (`google-services.json`, import Firebase di kode, meta-data di manifest).

### File Manifest
- **Lokasi:** `app/src/main/AndroidManifest.xml`
- **Aktivitas terkait autentikasi:**
  - `.ui.login.LoginActivity`
  - `.ui.register.RegisterActivity`
- **Firebase:** Ada meta-data untuk Crashlytics dan Performance.
- **Permissions:** INTERNET, ACCESS_NETWORK_STATE, dll.

### File/Kode Terkait Autentikasi
- **Login:**  
  - `LoginActivity` di manifest dan di folder login.
- **Register:**  
  - `RegisterActivity` di manifest dan di folder register.
- **Reset Password:**  
  - Ada variabel/fungsi terkait "reset" di `BaseEditText.kt` (fitur input password/reset field).
- **OAuth:**  
  - Tidak ditemukan file spesifik, namun ada penggunaan Firebase (bisa digunakan untuk autentikasi OAuth).
- **Verifikasi Email:**  
  - Tidak ditemukan secara eksplisit, perlu cek lebih lanjut di folder login/register.
- **Logout:**  
  - Tidak muncul eksplisit, biasanya ada di MainActivity atau utilitas user session.

---

## 2. API Contracts (Postman)

### Endpoint yang Ditemukan
- **Login:**  
  - `[POST] {{baseUrl}}/login`
  - Headers: Accept: application/json, Content-Type: application/json
  - Body:
    ```json
    {
      "email": "adminkj@gmail.com",
      "password": "Kerjajepang12$"
    }
    ```
- **Registrasi, Logout, Reset Password, Verifikasi Email, OAuth:**  
  - Tidak ditemukan endpoint khusus untuk fitur-fitur ini pada collection yang tersedia.
  - Untuk login OAuth, tidak ditemukan endpoint khusus (hanya ada akses ke Google Calendar, bukan autentikasi OAuth).

---

## 3. Desain UI & Metadata XML (Figma)

- **Status:**  
  - Tidak dapat diakses karena kendala teknis pada integrasi Figma MCP.
  - Solusi: Pastikan aplikasi Figma Desktop dan Dev Mode aktif, atau berikan akses/tautan ke file Figma yang ingin dianalisis.

---

## 4. Pedoman Coding Perusahaan & Best Practices (RAG)

- **Status:**  
  - Tidak dapat diakses karena RAG Agent tidak tersedia atau belum dikonfigurasi.
  - Solusi: Pastikan RAG Agent aktif atau minta akses ke dokumen pedoman perusahaan secara manual.

---

## 5. Analisis & Rekomendasi

### Ketersediaan Fitur
- **Login:** Tersedia baik di sisi Android (LoginActivity) maupun backend (endpoint `/login`).
- **Registrasi, Reset Password, Verifikasi Email, Logout, OAuth:**  
  - Belum ditemukan endpoint backend maupun file Android yang eksplisit.
  - Kemungkinan perlu implementasi tambahan di backend dan frontend.

### Integrasi Firebase
- Firebase sudah terintegrasi, sehingga fitur seperti login/register, reset password, verifikasi email, dan OAuth bisa diimplementasikan menggunakan Firebase Authentication jika backend belum mendukung.

### Kekurangan Informasi
- Tidak ada detail tentang password policy, rate limiting, role user, atau flow verifikasi email/reset password.
- Tidak ada akses ke desain UI/UX dan pedoman coding perusahaan.

---

## 6. Saran Implementasi

1. **Backend:**
   - Tambahkan endpoint untuk registrasi, reset password, verifikasi email, dan logout.
   - Implementasikan OAuth login (Google/Facebook) jika belum ada.
   - Pastikan ada dokumentasi API yang jelas.

2. **Frontend (Android):**
   - Implementasikan/cek ulang aktivitas: Login, Register, Reset Password, Verifikasi Email, Logout, dan OAuth.
   - Gunakan Firebase Authentication jika backend belum mendukung fitur-fitur di atas.

3. **Desain UI:**
   - Koordinasikan dengan tim desain untuk mendapatkan file Figma dan metadata XML terkait autentikasi.

4. **Pedoman Coding:**
   - Pastikan mengikuti best practices keamanan (password policy, rate limiting, validasi input, dsb).
   - Konsultasikan dengan tim terkait pedoman perusahaan.

---

## 7. Tindak Lanjut

- Konfirmasi kebutuhan endpoint baru ke tim backend.
- Minta akses ke file Figma dan dokumen pedoman perusahaan.
- Jika ingin detail kode atau endpoint, sebutkan file/endpoint spesifik yang ingin dieksplorasi.

---

**Catatan:**  
Jika Anda ingin saya menampilkan isi file Login/Register, mencari file lain terkait autentikasi, atau mendalami endpoint login, silakan konfirmasi instruksi berikutnya.