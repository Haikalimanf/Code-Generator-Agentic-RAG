# Technical Context for Issue #1

Berikut adalah laporan teknis komprehensif berdasarkan requirement dan hasil pencarian pada struktur project, manifest, serta best practices untuk implementasi sistem autentikasi pengguna yang aman di Android:

---

## 1. **Struktur Project & File Relevan (Android Studio)**

### a. **Struktur Project**
```
app/
  └── src/
      └── main/
          ├── java/com/mp/basemvvm/
          │   ├── ui/
          │   │   ├── login/           <-- LoginActivity, LoginViewModel
          │   │   └── register/        <-- RegisterActivity, RegisterViewModel
          │   ├── core/base/           <-- BaseActivity, BaseFragment (MVVM)
          │   ├── repository/          <-- Tempat implementasi Repository Pattern
          │   └── utils/               <-- Helper, Secure Storage, dsb
          ├── res/
          └── AndroidManifest.xml
```

### b. **File Manifest**
- `AndroidManifest.xml`:
  - Mendeklarasikan `LoginActivity`, `RegisterActivity`.
  - Permission: INTERNET, ACCESS_NETWORK_STATE.
  - Meta-data untuk Firebase, Google, Facebook.
  - Activity untuk Google/Facebook OAuth (`SignInHubActivity`, `FacebookActivity`).

### c. **Komponen Kode**
- **UI:** `LoginActivity.kt`, `RegisterActivity.kt`
- **MVVM:** `BaseActivity.kt`, `BaseFragment.kt`, ViewModel di masing-masing modul.
- **Repository:** Cari di package `repository` (untuk abstraksi data).
- **Secure Storage:** Kotpref diinisialisasi di `BaseApplication.kt` (bisa diganti/ditambah EncryptedSharedPreferences).
- **OAuth:** Dependency dan deklarasi manifest untuk Google/Facebook sudah ada.

---

## 2. **API Contracts (Backend Integration)**
> *Catatan: Jika menggunakan Firebase/Auth0, sebagian besar proses dilakukan via SDK. Jika backend custom, berikut pola umum API:*

### a. **Endpoint Umum**
- **POST /auth/register**  
  Request: `{ email, password }`  
  Response: `{ success, userId, message }`
- **POST /auth/login**  
  Request: `{ email, password }`  
  Response: `{ token, refreshToken, user, message }`
- **POST /auth/logout**  
  Header: `Authorization: Bearer <token>`
  Response: `{ success, message }`
- **POST /auth/password/reset**  
  Request: `{ email }`  
  Response: `{ success, message }`
- **POST /auth/email/verify**  
  Request: `{ email }`  
  Response: `{ success, message }`
- **POST /auth/oauth/google**  
  Request: `{ idToken }`  
  Response: `{ token, user }`
- **POST /auth/oauth/facebook**  
  Request: `{ accessToken }`  
  Response: `{ token, user }`

### b. **Error Handling**
- 400: Invalid input (email/password format, dsb)
- 401: Unauthorized (token invalid/expired)
- 409: Email already registered
- 500: Internal server error

---

## 3. **Pedoman Coding & Best Practices (Company Guidelines & Industry Standard)**

### a. **Keamanan**
- **HTTPS** WAJIB untuk semua komunikasi autentikasi.
- **Token** (JWT/session) disimpan di Secure Storage (`EncryptedSharedPreferences` atau Android Keystore).
- **Password** TIDAK BOLEH disimpan lokal.
- **Validasi Input** di sisi client & server (regex email, password strength).
- **Error Handling**: Tampilkan pesan jelas, jangan bocorkan detail teknis.

### b. **Integrasi OAuth**
- Ikuti guideline resmi Google/Facebook.
- Gunakan library resmi: `com.google.android.gms:play-services-auth`, `com.facebook.android:facebook-login`.
- Jangan hardcode client secret di aplikasi.

### c. **Arsitektur**
- **MVVM**: ViewModel untuk logic, LiveData/StateFlow untuk state.
- **Repository Pattern**: Abstraksi data source (remote/local).
- **UseCase**: Pisahkan logic bisnis autentikasi.
- **UI**: Activity/Fragment untuk form login, register, reset, verifikasi, tombol OAuth.

### d. **Pengiriman Email**
- Email verifikasi & reset password harus otomatis (via backend/Firebase).
- Jangan kirim email manual dari aplikasi.

### e. **Library**
- Gunakan library yang didukung komunitas dan aktif (Firebase Auth, Auth0, Google/Facebook SDK).

---

## 4. **Technical Impact**

- **UI:** Form registrasi, login, reset password, verifikasi email, tombol login Google/Facebook.
- **Data:** Model user, session/token management, penyimpanan status autentikasi.
- **Domain:** Use case autentikasi, validasi, integrasi OAuth, pengiriman email verifikasi/reset.

---

## 5. **Constraints**

- Semua komunikasi autentikasi via HTTPS.
- OAuth mengikuti guideline resmi.
- Tidak menyimpan password lokal.
- Email verifikasi/reset otomatis.
- Library pihak ketiga harus terbukti dan didukung komunitas.

---

## 6. **Rekomendasi Implementasi**

- **Gunakan Firebase Auth** jika ingin cepat, atau backend custom dengan pola API di atas.
- **MVVM + Repository Pattern** untuk maintainability.
- **Secure Storage** untuk token/session.
- **Validasi input** di semua form.
- **Error handling** user-friendly.
- **Integrasi OAuth** via SDK resmi.

---

**Jika Anda ingin detail kode, contoh ViewModel, Repository, atau flow diagram, silakan sebutkan!**