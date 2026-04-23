# Technical Context for Issue #1

Berikut adalah laporan teknis komprehensif berdasarkan requirement sistem autentikasi pengguna yang Anda berikan, dengan mengacu pada struktur project Android, integrasi backend (API), dan pedoman best practices perusahaan (RAG):

---

## 1. Struktur Project & File Relevan (Android Studio)

### a. Struktur Project
- **Folder utama autentikasi:**
  - `app/src/main/java/com/mp/basemvvm/ui/login/` (logic login)
  - `app/src/main/java/com/mp/basemvvm/ui/register/` (logic registrasi)
- **Komponen pendukung:**
  - `BaseEditText.kt` (input password, reset, dsb)
  - `BaseDialog.kt`, `BaseDialogInterface.kt` (dialog konfirmasi/error)
  - `BaseActivity.kt`, `BaseFragment.kt` (base logic, kemungkinan integrasi third party)
- **Resource:**
  - `app/src/main/AndroidManifest.xml` (daftar activity, permission, integrasi third party)
  - File konfigurasi seperti `google-services.json` (untuk Firebase/Google Sign-In)

### b. AndroidManifest.xml
- Activity terkait autentikasi:
  - `com.mp.basemvvm.ui.register.RegisterActivity`
  - `com.mp.basemvvm.ui.login.LoginActivity`
- Integrasi third party:
  - Google Sign-In: `com.google.android.gms.auth.api.signin.internal.SignInHubActivity`
  - Facebook Login: `com.facebook.FacebookActivity`
  - Firebase Auth: meta-data dan permission terkait

---

## 2. Integrasi Backend (API Contracts)

- **Tidak ditemukan API contract autentikasi** (registrasi, login, logout, reset password, verifikasi email, OAuth) pada koleksi API yang tersedia saat ini.
- Semua endpoint yang ada hanya terkait dengan fitur link shortener, redirect, statistik link, dan QR code.
- **Kesimpulan:** Jika fitur autentikasi membutuhkan backend, endpoint baru harus dibuat atau gunakan koleksi API lain yang memang menyediakan fitur autentikasi.

---

## 3. Pedoman Coding Perusahaan & Best Practices (RAG)

- **RAG tidak tersedia** saat ini, sehingga tidak ada pedoman coding perusahaan yang bisa diambil secara otomatis.
- **Rekomendasi best practices umum:**
  - Gunakan enkripsi untuk penyimpanan password (hash + salt, misal bcrypt/argon2).
  - Implementasikan rate limiting pada endpoint login/reset password.
  - Gunakan token berbasis JWT untuk sesi autentikasi.
  - Untuk verifikasi email, gunakan link unik dengan token yang kadaluarsa.
  - OAuth: gunakan library resmi Google/Facebook, pastikan validasi token di backend.
  - Jangan pernah menyimpan credential OAuth di client.
  - Terapkan password policy (minimal panjang, kombinasi karakter).
  - Pastikan semua komunikasi dengan backend menggunakan HTTPS.

---

## 4. Rangkuman & Rekomendasi Implementasi

### a. Android (Client)
- Implementasi logic autentikasi di folder `login` dan `register`.
- Gunakan activity yang sudah terdaftar di manifest.
- Integrasi Google/Facebook Sign-In menggunakan SDK resmi.
- Untuk reset password dan verifikasi email, siapkan UI/UX di activity/fragment terkait.
- Pastikan semua data sensitif (token, credential) disimpan dengan aman (misal: EncryptedSharedPreferences).

### b. Backend (API)
- Karena belum ada API contract, perlu:
  - Mendesain endpoint: `/register`, `/login`, `/logout`, `/reset-password`, `/verify-email`, `/oauth/google`, `/oauth/facebook`.
  - Mendefinisikan response dan error handling yang konsisten.
  - Menyediakan dokumentasi API untuk integrasi dengan mobile app.

### c. Keamanan & Best Practices
- Terapkan best practices keamanan seperti di atas.
- Pastikan ada mekanisme verifikasi email sebelum akun aktif.
- OAuth hanya digunakan untuk login (atau registrasi jika user baru).
- Audit dan review kode secara berkala.

---

## 5. Catatan Ambiguitas
- Tidak ada detail framework/library yang wajib.
- Alur verifikasi email (link/OTP) perlu diputuskan.
- Password policy dan rate limiting perlu ditentukan.
- OAuth: perlu kejelasan apakah hanya untuk login atau juga registrasi.
- UI/UX perlu didesain sesuai kebutuhan.

---

**Jika Anda membutuhkan detail kode, contoh API contract, atau pedoman spesifik dari perusahaan, silakan aktifkan akses RAG atau sediakan referensi tambahan.**