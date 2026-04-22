# Technical Context for Issue #1

Berikut adalah hasil kompilasi konteks teknis yang berhasil dikumpulkan untuk implementasi sistem autentikasi pengguna sesuai requirement Anda:

---

## 1. Struktur Project & File Relevan (Android Studio)

**Struktur Folder:**
```
📁 app/
  └── src/
      └── main/
          ├── java/
          │   └── com/
          │       └── mp/
          │           └── basemvvm/
          │               └── ui/
          │                   ├── login/        ← LoginActivity
          │                   └── register/     ← RegisterActivity
          ├── res/
          │   └── layout/      ← Layout XML untuk login/register
          └── AndroidManifest.xml
```

**File Manifest:**
- Lokasi: `app/src/main/AndroidManifest.xml`
- Aktivitas terkait autentikasi:
  - `.ui.register.RegisterActivity`
  - `.ui.login.LoginActivity`
- Permission penting:
  - `android.permission.INTERNET`
  - `android.permission.ACCESS_NETWORK_STATE`
  - `com.google.android.gms.permission.AD_ID` (terkait Google)
- Ada meta-data Google Analytics.

**File & Kode yang Relevan:**
- `LoginActivity.kt` dan `RegisterActivity.kt` (logika utama login/registrasi)
- `BaseEditText.kt` (fungsi terkait password, reset, dsb)
- `BaseDialog.kt`, `BaseDialogInterface.kt` (dialog konfirmasi/error)
- Import `com.google.firebase.*` dan `com.google.android.material.*` (indikasi Firebase & Material Design)
- Penggunaan `com.facebook.shimmer.ShimmerFrameLayout` (indikasi library Facebook sudah digunakan)
- Untuk reset password dan verifikasi email kemungkinan ada di dalam folder/fungsi login/register.
- Untuk OAuth, ada permission dan meta-data terkait Google, namun file spesifik OAuth belum ditemukan (perlu cek lebih lanjut di folder login).

---

## 2. API Contracts (Backend Integration)

**Status:**  
Belum ditemukan detail API contracts untuk:
- Registrasi
- Login
- Logout
- Reset password
- Verifikasi email
- OAuth (Google/Facebook)

**Catatan:**  
Biasanya, API contracts untuk fitur ini meliputi endpoint seperti:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/reset-password`
- `POST /auth/verify-email`
- `POST /auth/oauth/google`
- `POST /auth/oauth/facebook`

Endpoint ini biasanya menerima/mengembalikan data dalam format JSON, dan membutuhkan integrasi token (JWT atau sejenisnya) untuk autentikasi.

---

## 3. Pedoman Coding Perusahaan / Best Practices

**Status:**  
Tidak ditemukan pedoman atau best practices perusahaan secara spesifik untuk autentikasi pada saat ini.

**Best practices umum yang biasanya berlaku:**
- Gunakan HTTPS untuk semua komunikasi API.
- Simpan token autentikasi secara aman (misal: EncryptedSharedPreferences).
- Terapkan validasi input pada sisi client dan server.
- Implementasikan rate limiting dan password policy.
- Untuk OAuth, gunakan library resmi Google/Facebook dan pastikan proses login/registrasi berjalan seamless.
- Untuk verifikasi email, biasanya menggunakan link unik yang dikirim ke email pengguna.

---

## 4. Rangkuman Teknis

- **File utama:** `LoginActivity.kt`, `RegisterActivity.kt`, layout XML terkait, dan manifest.
- **Komponen pendukung:** Utility/helper untuk password, dialog, dan integrasi OAuth.
- **Integrasi backend:** Perlu konfirmasi endpoint API yang akan digunakan.
- **Integrasi OAuth:** Ada indikasi library Google & Facebook sudah terpasang, perlu cek implementasi detail di folder login.
- **Keamanan:** Pastikan penggunaan permission yang tepat dan penyimpanan token yang aman.

---

### **Langkah Selanjutnya yang Disarankan**
1. Audit isi file `LoginActivity.kt` dan `RegisterActivity.kt` untuk melihat implementasi saat ini.
2. Konfirmasi detail API contracts dengan tim backend.
3. Jika perlu, cek layout XML dan helper OAuth untuk integrasi UI/UX.
4. Pastikan semua permission dan meta-data di manifest sudah sesuai kebutuhan autentikasi modern.

Jika Anda ingin detail isi file tertentu atau ingin menelusuri lebih lanjut (misal: layout, helper OAuth, dsb), silakan informasikan file/folder mana yang ingin difokuskan.