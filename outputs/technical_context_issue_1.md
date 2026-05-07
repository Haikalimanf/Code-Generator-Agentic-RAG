# Technical Context for Issue #1

Berikut adalah laporan teknis komprehensif berdasarkan requirement dan hasil pencarian lintas sistem:

---

## 1. Struktur & File Project (Android Studio)

**Struktur utama:**
- Modul: `app`
- Kode utama: `app/src/main/java/com/mp/basemvvm/`
- Manifest: `app/src/main/AndroidManifest.xml`
- Resource: `app/src/main/res/`

**File penting terkait autentikasi:**
- `LoginActivity.kt` — untuk login pengguna
- `RegisterActivity.kt` — untuk registrasi pengguna
- `BaseEditText.kt` — banyak fungsi terkait input email/password, reset password
- `BaseActivity.kt`, `BaseFragment.kt` — basis untuk aktivitas dan fragment, mengatur lifecycle dan kemungkinan handling autentikasi global
- `BaseApplication.kt` — inisialisasi aplikasi, ada import Firebase
- `AndroidManifest.xml` — mendeklarasikan activity, permission (INTERNET, ACCESS_NETWORK_STATE), meta-data Google Analytics (indikasi integrasi Google/Firebase)
- `google-services.json` — konfigurasi Firebase/Google Sign-In

**Indikasi integrasi:**
- Firebase (import di beberapa file)
- Google (meta-data dan permission)
- Facebook (ada import shimmer, perlu dicek lebih lanjut untuk OAuth)

---

## 2. API Contracts (Postman)

**Endpoint yang ditemukan:**
- **Login**
  - [POST] `{{base_url}}/login`
  - Body: `{ "email": "...", "password": "..." }`
- **Google Calendar**
  - [GET] Google Calendar API (bukan endpoint login OAuth, hanya akses data setelah login Google)

**Catatan:**
- Tidak ditemukan endpoint untuk registrasi, logout, reset password, atau verifikasi email.
- Tidak ada endpoint eksplisit untuk login OAuth Google/Facebook.
- Kemungkinan login OAuth dilakukan di sisi client (Android) dan backend hanya menerima token Google/Facebook untuk diverifikasi.

---

## 3. Desain UI & XML (Figma)

**Status:**  
Gagal mengambil data dari Figma. Tidak ada desain UI atau metadata XML yang bisa diambil secara otomatis.

**Saran:**  
- Cek langsung ke file Figma tim desain untuk referensi tampilan halaman login, registrasi, reset password, dan login OAuth.
- Biasanya, halaman-halaman ini memiliki komponen: input email/password, tombol login/daftar, tombol "Lupa Password", dan tombol login Google/Facebook.

---

## 4. Pedoman Coding & Best Practices (RAG)

**Status:**  
Tidak dapat mengakses pedoman coding perusahaan atau best practices secara otomatis.

**Saran umum best practices:**
- **Password Policy:** Minimal 8 karakter, kombinasi huruf besar, kecil, angka, dan simbol.
- **Rate Limiting:** Batasi percobaan login untuk mencegah brute force.
- **Verifikasi Email:** Kirim link verifikasi ke email pengguna baru.
- **OAuth:** Gunakan library resmi Google/Facebook, simpan token secara aman, lakukan validasi token di backend.
- **Reset Password:** Kirim link reset ke email, link hanya berlaku dalam waktu tertentu.
- **Keamanan:** Gunakan HTTPS, simpan password dengan hash (bcrypt/argon2), jangan log data sensitif.

---

## 5. Gap & Ambiguitas

- Tidak ada detail API untuk registrasi, reset password, verifikasi email, atau logout.
- Tidak ada detail flow OAuth (apakah hanya login atau juga registrasi).
- Tidak ada pedoman UI/UX atau tampilan halaman.
- Tidak ada pedoman keamanan spesifik dari perusahaan.

---

## 6. Rekomendasi Implementasi

1. **Android:**
   - Gunakan `LoginActivity` dan `RegisterActivity` untuk UI login/registrasi.
   - Integrasikan Google/Facebook Sign-In menggunakan SDK resmi.
   - Gunakan Firebase Auth jika backend belum menyediakan endpoint lengkap.
   - Implementasikan reset password dan verifikasi email via Firebase atau backend jika tersedia.

2. **Backend:**
   - Tambahkan endpoint untuk registrasi, reset password, verifikasi email, dan logout.
   - Implementasikan validasi token OAuth Google/Facebook.
   - Terapkan password policy dan rate limiting.

3. **UI/UX:**
   - Konsultasikan dengan tim desain untuk mendapatkan mockup halaman autentikasi.
   - Pastikan ada feedback error yang jelas untuk pengguna.

4. **Keamanan:**
   - Terapkan best practices seperti di atas.
   - Audit kode untuk memastikan tidak ada data sensitif yang bocor.

---

## 7. Next Steps

- Konfirmasi dengan tim backend terkait endpoint yang belum tersedia.
- Koordinasi dengan tim desain untuk mendapatkan file Figma.
- Minta pedoman coding perusahaan secara manual jika diperlukan.
- Review dan update manifest serta dependencies untuk memastikan semua permission dan library sudah sesuai.

---

**Jika Anda ingin melihat isi file tertentu (misal: LoginActivity, RegisterActivity, BaseEditText) atau ingin penjelasan arsitektur autentikasi secara lebih detail, silakan informasikan file atau topik yang ingin didalami!**