from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class GitLabAnalysis(BaseModel):
    role: str = Field(description="Siapa pengguna/aktor yang menjadi subjek cerita. Contoh: 'customer', 'admin', 'registered user'.")
    goal: str = Field(description="Apa yang ingin dicapai oleh pengguna. Dimulai dengan kata kerja. Contoh: 'track my order status'.")
    benefit: str = Field(description="Manfaat atau nilai yang didapat pengguna. Contoh: 'stay updated on my deliveries'.")
    story: str = Field(description="User story lengkap dalam format baku: 'As a [role], I want [goal], so that [benefit]'.")


class PostmanAPIAnalysis(BaseModel):
    model_config = ConfigDict(json_schema_extra={"additionalProperties": False})
    feature_summary: str = Field(description="Ringkasan fitur yang dianalisis.")
    relevant_endpoints: List[str] = Field(description="Daftar endpoint yang relevan dalam format 'METHOD /path — deskripsi singkat'.")
    api_contracts: List[str] = Field(description="Detail contract untuk setiap endpoint dalam format teks.")
    missing_endpoints: List[str] = Field(description="Daftar fitur yang tidak ditemukan endpointnya di collection.")
    recommendations: Optional[str] = Field(default=None, description="Rekomendasi integrasi atau catatan tambahan.")


class AndroidArchitectureAnalysis(BaseModel):
    model_config = ConfigDict(json_schema_extra={"additionalProperties": False})
    overview: str = Field(description="Ringkasan struktur proyek secara umum.")
    key_components: List[str] = Field(description="Daftar komponen utama dan perannya.")
    data_flow: str = Field(description="Penjelasan bagaimana data mengalir antar komponen.")
    relevant_files: List[str] = Field(description="Daftar path file yang krusial untuk dipahami.")
    architectural_patterns: List[str] = Field(description="Pola arsitektur yang terdeteksi.")
    recommendations: Optional[str] = Field(default=None, description="Saran atau rekomendasi arsitektur jika ada.")


class FigmaDesignAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    feature_name: str = Field(description="Nama fitur atau halaman yang dianalisis.")
    node_id: str = Field(description="ID node utama yang dianalisis.")
    structure_summary: str = Field(description="Ringkasan struktur UI (XML).")
    key_components: List[dict] = Field(description="Daftar komponen penting dan ID-nya.")
    xml_context: str = Field(description="Potongan XML metadata yang paling relevan.")
    design_notes: Optional[str] = Field(default=None, description="Catatan tambahan mengenai desain atau styling.")


class ComplianceAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_classes: str = Field(description="Daftar base class Kotlin yang wajib digunakan beserta penjelasan kapan menggunakannya.")
    naming_kotlin: str = Field(description="Aturan konvensi penamaan file dan class Kotlin (Activity, Fragment, ViewModel, UseCase, Repository, dsb).")
    naming_xml: str = Field(description="Aturan konvensi penamaan layout dan resource XML.")
    naming_view_id: str = Field(description="Aturan konvensi penamaan ID komponen UI (View ID).")
    naming_method_variable: str = Field(description="Aturan konvensi penamaan method, fungsi, variabel, package, dan konstanta Kotlin.")
    recommendations: Optional[str] = Field(default=None, description="Saran atau rekomendasi implementasi khusus agar sesuai dengan standar perusahaan.")
    relevant_sections: List[str] = Field(description="Daftar referensi bab atau halaman dokumen internal perusahaan yang dirujuk.")


class SpecialistTask(BaseModel):
    """Sub-tugas terstruktur untuk satu agen spesialis (hasil dekomposisi Planner).

    Mengimplementasikan prinsip Context Engineering: setiap agen hanya menerima
    instruksi dan konteks yang paling relevan untuk tugasnya, BUKAN seluruh User Story.
    """
    model_config = ConfigDict(extra="forbid")

    task: str = Field(
        description="Instruksi spesifik dan terfokus untuk agen ini. BUKAN user story mentah, "
        "melainkan perintah yang sudah di-engineer khusus untuk domain agen ini. "
        "Hanya berisi konteks yang relevan bagi agen ini."
    )
    focus_areas: List[str] = Field(
        description="Aspek-aspek spesifik yang harus difokuskan oleh agen ini."
    )
    context_scope: str = Field(
        description="Cakupan konteks dari User Story yang perlu agen ini ketahui. "
        "Hanya bagian yang relevan dengan domain agen ini."
    )
    expected_output: str = Field(
        description="Jenis output yang diharapkan dari agen ini untuk mendukung integrasi keseluruhan."
    )


class PlannerDecision(BaseModel):
    """Keputusan Planner: dekomposisi tugas dengan Context Engineering.

    Menggunakan field eksplisis per-agen (bukan Dict) agar kompatibel dengan
    OpenAI Structured Outputs yang tidak mendukung additionalProperties Dict[str, T].
    Setiap agen menerima PLAN yang UNIK dan TERFOKUS, bukan user story mentah.
    """
    model_config = ConfigDict(extra="forbid")

    # <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
    # android_studio: Optional[SpecialistTask] = Field(
    #     default=None,
    #     description="Plan/tugas khusus untuk agen Android Studio. None jika tidak diperlukan."
    # )
    # <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
    # postman: Optional[SpecialistTask] = Field(
    #     default=None,
    #     description="Plan/tugas khusus untuk agen Postman. None jika tidak diperlukan."
    # )
    # <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
    # figma: Optional[SpecialistTask] = Field(
    #     default=None,
    #     description="Plan/tugas khusus untuk agen Figma. None jika tidak diperlukan."
    # )
    rag: Optional[SpecialistTask] = Field(
        default=None,
        description="Plan/tugas khusus untuk agen RAG. None jika tidak diperlukan."
    )
    reasoning: str = Field(
        description="Penalaran Planner mengenai mengapa tugas dipecah dengan cara ini, "
        "konteks apa yang dilewatkan ke agen mana, dan mengapa agen tertentu tidak diikutsertakan."
    )