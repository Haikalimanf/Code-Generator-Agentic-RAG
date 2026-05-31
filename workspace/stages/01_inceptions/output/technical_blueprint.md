# Technical Integration Context Blueprint


---

## Kebutuhan Sistem / Requirement

- **Role**: mobile developer
- **Goal**: mengimplementasikan sistem autentikasi pengguna yang aman dengan fitur registrasi, login/logout, reset password, verifikasi email, dan opsi login via OAuth
- **Benefit**: memastikan hanya pengguna yang terverifikasi yang dapat mengakses aplikasi, meningkatkan keamanan, dan memberikan kemudahan akses melalui berbagai metode login
- **User Story**: As a mobile developer, I want to implement a secure user authentication system with registration, login/logout, password reset, email verification, and OAuth login options, so that only verified users can access the app securely and conveniently.


---

**Specialist Agents Terlibat**: `rag`


---

### Rincian Plan Hasil Dekomposisi (Planner → Context Engineering)

---



---

#### `rag`

---

- **Task**: Kueri koleksi 'company_guidelines' pada Vector DB untuk dua dokumen: 'Suitcore Android MVVM Documentation V1' dan 'SuitMobile Code Style [Android] - Naming - Version 2'. Ekstrak aturan dan pedoman yang relevan untuk: struktur folder MVVM, pola ViewModel, konvensi penamaan class dan method, serta standar keamanan autentikasi (jika tersedia) yang harus diterapkan pada fitur: registrasi, login/logout, reset password, verifikasi email, dan OAuth login.

---

- **Focus Areas**: struktur folder MVVM untuk fitur autentikasi, pola ViewModel untuk autentikasi, konvensi penamaan class dan method terkait autentikasi, standar keamanan autentikasi (jika ada)

---

- **Context Scope**: Bagian requirement yang menyangkut implementasi autentikasi user (registrasi, login/logout, reset password, verifikasi email, OAuth login) dan kebutuhan keamanan serta konvensi coding yang berlaku di perusahaan.

---

- **Expected Output**: Ringkasan terstruktur berisi aturan dan pedoman coding yang wajib diikuti untuk implementasi fitur autentikasi, mencakup struktur folder, pola ViewModel, konvensi penamaan, dan standar keamanan (jika ada), diambil dari dokumen yang disebutkan.

---



---

## Pedoman Coding & Best Practices (RAG)

#### 2. Base Class yang Wajib Digunakan

- **BaseActivity<VB: ViewBinding>**: Digunakan untuk semua Activity baru agar mendapatkan property dan method standar Suitcore. 
- **BaseFragment<VB: ViewBinding>**: Digunakan untuk semua Fragment baru untuk konsistensi dan reusability. 
- **BaseViewModel<Event, State>**: Digunakan untuk semua ViewModel baru agar mengikuti arsitektur MVVM Suitcore dan mendapatkan property/method standar. 
- **BaseRecyclerViewAdapter<T>**: Digunakan untuk semua adapter RecyclerView agar konsisten dalam pengelolaan list.

#### 3. Naming Conventions — File & Class (Kotlin)

- **Activity**: `{Feature}Activity.kt` → class `{Feature}Activity` (PascalCase)
- **Fragment**: `{Feature}Fragment.kt` → class `{Feature}Fragment` (PascalCase)
- **ViewModel**: `{Feature}ViewModel.kt` → class `{Feature}ViewModel` (PascalCase)
- **UseCase**: `{Feature}UseCase.kt` → class `{Feature}UseCase` (PascalCase)
- **Repository**: `{Feature}Repository.kt` → class `{Feature}Repository` (PascalCase)
- **Model/Response**: `{Feature}Response.kt` / `{Feature}Model.kt` (PascalCase)
- **Event**: `{Feature}Event` (sealed class, PascalCase)
- **State**: `{Feature}State` (data class, PascalCase)

#### 4. Naming Conventions — Layout & Resource XML

- **Layout Activity**: `activity_{feature_name}.xml` (snake_case)
- **Layout Fragment**: `fragment_{feature_name}.xml` (snake_case)
- **Layout Item List**: `item_{description}.xml` (snake_case)
- **Layout komponen reusable**: `view_{description}.xml` (snake_case)
- **Drawable button background**: `bg_button_{value_name}.xml` (snake_case)
- **Drawable icon**: `ic_{name}.xml` (snake_case)
- **Color**: `color_{name}` (snake_case)

#### 5. Naming Conventions — ID Komponen UI (View ID)

- **TextView**: `tv{ValueName}`
- **EditText**: `et{ValueName}`
- **Button**: `btn{ActionName}`
- **ImageView**: `img{ValueName}`
- **RecyclerView**: `rv{ListName}`
- **ProgressBar**: `progressBar{ValueName}`

#### 6. Naming Conventions — Method & Variabel (Kotlin)

- **Method/Function**: camelCase, diawali kata kerja → contoh: `getUser()`, `handleLogin()`, `onLoginSuccess()`
- **Variabel**: camelCase → contoh: `userName`, `isLoading`, `authToken`
- **Private property**: `_camelCase` dengan backing property → contoh: `_uiState`
- **Constant**: SCREAMING_SNAKE_CASE → contoh: `MAX_RETRY_COUNT`, `BASE_URL`
- **Package/Folder**: huruf kecil semua, tanpa pemisah → contoh: `login`, `register`, `data`

#### 7. Rekomendasi Implementasi

- **Struktur Folder MVVM**: Pisahkan kode ke dalam layer sesuai Clean Architecture: `core`, `data`, `domain`, `ui`, dan `feature`.
- **Pola ViewModel**: Selalu inherit dari `BaseViewModel`, gunakan event dan state yang jelas untuk setiap fitur (misal: `LoginEvent`, `LoginState`).
- **Autentikasi & OAuth**: Untuk login sosial (Google, Facebook), gunakan modul Social Auth yang sudah disediakan Suitcore.
- **Pengelolaan API**: Gunakan `ApiService` di layer data, pastikan pengelolaan thread dan error handling tidak mengganggu main thread.
- **Model Parsing**: Untuk response autentikasi, gunakan model parsing manual (json deserializer) atau otomatis (RoboPOJOGenerator) sesuai kebutuhan.

**Catatan:**
Tidak ditemukan standar keamanan autentikasi spesifik (misal: password hashing, token storage) di dokumen internal. Gunakan best practice Android dan library resmi untuk keamanan autentikasi.

#### Referensi Dokumen Internal

- Suitcore Android MVVM Documentation V1, Hal: 0, 7, 13, 27, 29, 33, 36, 47
- SuitMobile Code Style [Android] - Naming - Version 2, Hal: 0