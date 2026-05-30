import sys
import logging
import traceback
import math
from typing import Any

import gitlab
import gitlab.exceptions
from langchain_core.tools import tool

from src.config.settings import settings
from src.models.schemas import GitLabAnalysis
from src.utils.error_handler import wrap_tool_call
from src.utils.llm_factory import create_llm, create_agent_with_memory, execute_agent_and_structure

# Impor modul eksperimen untuk kebutuhan semantic clustering & uncertainty pre-check
from experiment.uncertainty.semantic_clustering import semantic_clustering, load_embeddings_model

logger = logging.getLogger("gitlab_agent")

def _get_gitlab_client() -> gitlab.Gitlab:
    if not settings.gitlab_token:
        raise ValueError("GITLAB_TOKEN tidak ditemukan di environment variable.")

    gl = gitlab.Gitlab(settings.gitlab_url, private_token=settings.gitlab_token)
    try:
        gl.auth()
        return gl
    except gitlab.exceptions.GitlabAuthenticationError:
        raise ConnectionError("Gagal autentikasi ke GitLab. Periksa GITLAB_TOKEN Anda.")
    except Exception as e:
        raise ConnectionError(f"Gagal terhubung ke GitLab: {e}")


def _extract_issue_attrs(issue: Any) -> dict[str, Any]:
    attrs: dict[str, Any] = issue.attributes if hasattr(issue, "attributes") else {}
    return {
        "title": attrs.get("title", ""),
        "state": attrs.get("state", ""),
        "labels": attrs.get("labels", []),
        "description": attrs.get("description", ""),
    }


def _extract_gitlab_issue_specs_impl(project_id: str, issue_iid: int) -> str:
    """
    Fungsi internal untuk mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.
    """
    logger.info("Connecting to project %s, issue #%s...", project_id, issue_iid)

    gl = _get_gitlab_client()

    try:
        # Use the REST API directly to avoid TypeVar generic issues
        # that confuse Pyrefly and other type checkers.
        project: Any = gl.projects.get(project_id, lazy=True)
        issue = project.issues.get(issue_iid)

        issue_attrs = _extract_issue_attrs(issue)
        description: str = issue_attrs["description"] or ""
        desc_size = len(description)

        logger.info("Fetching issue: '%s' (Desc size: %d chars)", issue_attrs["title"], desc_size)

        spec_data: dict[str, Any] = {
            "title": issue_attrs["title"],
            "state": issue_attrs["state"],
            "labels": issue_attrs["labels"],
            "description": description,
            "comments": [],
        }

        notes = issue.notes.list(all=True)
        for note in notes:
            if not note.system:
                spec_data["comments"].append({
                    "author": note.author["username"],
                    "body": note.body,
                })

        comments_count = len(spec_data["comments"])
        comments_size = sum(len(c["body"]) for c in spec_data["comments"])
        logger.info("Found %d human comments (Total size: %d chars)", comments_count, comments_size)

        formatted_spec = (
            f"Fitur/Issue: {spec_data['title']}\n"
            f"Status: {spec_data['state']}\n"
            f"Labels: {', '.join(spec_data['labels'])}\n"
            f"Deskripsi:\n{spec_data['description']}\n\n"
            f"Komentar Diskusi:\n"
        )

        for c in spec_data["comments"]:
            formatted_spec += f"- {c['author']}: {c['body']}\n"

        logger.info("Total Context Size: %d chars", len(formatted_spec))
        return formatted_spec

    except gitlab.exceptions.GitlabGetError as e:
        return f"Error: Project atau Issue tidak ditemukan (HTTP {e.response_code})."
    except Exception as e:
        return f"Terjadi kesalahan tak terduga saat mengambil data GitLab: {e}"


@tool
@wrap_tool_call
def extract_gitlab_issue_specs(project_id: str, issue_iid: int) -> str:
    """
    Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.

    Args:
        project_id: ID dari project GitLab
        issue_iid: Internal ID dari issue
    """
    return _extract_gitlab_issue_specs_impl(project_id, issue_iid)


SYSTEM_PROMPT_GITLAB = (
    "Anda adalah 'The Story Writer', agen ahli dalam menganalisis kebutuhan perangkat lunak dari GitLab "
    "dan mengubahnya menjadi satu User Story yang terstruktur sesuai best practice.\n\n"

    "Tugas Anda:\n"
    "1. Panggil tool extract_gitlab_issue_specs untuk mendapatkan data lengkap dari issue.\n"
    "2. Baca dan pahami seluruh deskripsi, label, dan komentar pada issue tersebut.\n"
    "3. Identifikasi aktor/pengguna UTAMA yang paling relevan dengan inti kebutuhan issue ini.\n"
    "4. Susun SATU User Story yang merepresentasikan kebutuhan utama dari issue tersebut.\n\n"

    "FORMAT USER STORY (WAJIB DIIKUTI):\n"
    "User story HARUS ditulis dalam format berikut:\n"
    "  'As a [role], I want [goal], so that [benefit].'\n"
    "  - Role   : Pengguna disini adalah mobile developer.\n"
    "  - Goal   : Apa yang ingin dicapai mobile developer (dimulai dengan kata kerja aktif).\n"
    "  - Benefit: Nilai/manfaat yang didapat mobile developer dari fitur ini (jelaskan 'mengapa' ini penting).\n\n"

    "ATURAN:\n"
    "1. Hanya gunakan fakta dari teks issue dan komentar.\n"
    "2. Jangan menebak teknologi, nama class, atau direktori jika tidak disebutkan secara eksplisit.\n"
    "3. Pilih SATU aktor utama dan SATU tujuan inti — jangan gabungkan banyak kebutuhan dalam satu story.\n\n"

    "STRUKTUR OUTPUT:\n"
    "1. **Role**: mobile developer.\n"
    "2. **Goal**: Apa yang ingin dicapai mobile developer (kata kerja aktif).\n"
    "3. **Benefit**: Nilai yang didapat mobile developer dari fitur ini.\n"
    "4. **Story**: User story lengkap: 'As a [role], I want [goal], so that [benefit].'\n"

    "Berikan output yang objektif, berbasis data, dan dapat langsung digunakan oleh tim development."
)

SYSTEM_PROMPT_SAMPLING = (
    "Anda adalah analis kebutuhan perangkat lunak yang sedang melakukan sesi brainstorming. "
    "Tugas Anda adalah membaca deskripsi issue dan komentar diskusi tim, "
    "lalu menulis SATU User Story yang Anda anggap paling masuk akal berdasarkan konteks yang ada.\n\n"

    "ATURAN PENTING:\n"
    "1. Panggil tool extract_gitlab_issue_specs untuk mendapatkan data issue.\n"
    "2. Jika terdapat ambiguitas atau konflik interpretasi dalam komentar, "
    "pilih SALAH SATU interpretasi yang paling Anda yakin benar — jangan menyebutkan konfliknya.\n"
    "3. User story ditulis dari sudut pandang 'mobile developer'.\n"
    "4. Format wajib: 'As a mobile developer, I want [goal], so that [benefit].'\n"
    "5. Tetap ringkas: maksimal 2 kalimat untuk bagian goal dan benefit.\n\n"

    "Berikan output langsung sebagai satu User Story tanpa penjelasan tambahan."
)


def post_gitlab_comment(project_id: str, issue_iid: int, message: str) -> None:
    """
    Mengirim komentar (note) ke GitLab Issue untuk keperluan eskalasi klarifikasi.
    """
    logger.info("Mengirim komentar eskalasi ke GitLab project %s issue #%s...", project_id, issue_iid)
    try:
        gl = _get_gitlab_client()
        project: Any = gl.projects.get(project_id, lazy=True)
        issue = project.issues.get(issue_iid)
        issue.notes.create({"body": message})
        logger.info("Komentar eskalasi berhasil dikirim.")
    except Exception as e:
        logger.error("Gagal mengirim komentar eskalasi ke GitLab: %s", e)


def run_gitlab_analyst_agent(project_id: str, issue_iid: int) -> GitLabAnalysis:
    # ─── PRE-FETCH CONTEXT ───
    # Ambil spesifikasi issue sekali saja di awal untuk menghindari rate limit API call berulang
    logger.info("Mengambil context GitLab issue sekali di awal...")
    issue_context = _extract_gitlab_issue_specs_impl(project_id, issue_iid)
    
    if issue_context.startswith("Error:") or issue_context.startswith("Terjadi kesalahan"):
        raise ValueError(f"Gagal mengambil issue dari GitLab: {issue_context}")

    # Tool bayangan untuk mengembalikan context lokal (tanpa memanggil API GitLab berulang)
    @tool("extract_gitlab_issue_specs")
    def mock_extract_tool(project_id: str, issue_iid: int) -> str:
        """
        Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.
        """
        return issue_context

    # ─── FASE 1: UNCERTAINTY SAMPLING & SCORING ───
    logger.info("Memulai Fase 1: Uncertainty Sampling (M=5)...")
    sampling_llm = create_llm(temperature=1.0, max_tokens=1024)
    samples = []
    
    for i in range(5):
        thread_id = f"sampling_{project_id}_{issue_iid}_sample_{i}"
        sampling_executor, sampling_config = create_agent_with_memory(
            llm=sampling_llm,
            tools=[mock_extract_tool],
            system_prompt=SYSTEM_PROMPT_SAMPLING,
            agent_name="GitLabAnalyst_Sampling",
            thread_id=thread_id,
        )
        
        user_input = f"Tolong analisis issue #{issue_iid} pada project {project_id} dan buatkan satu User Story yang merepresentasikan kebutuhan utama dari issue tersebut."
        
        try:
            res: GitLabAnalysis = execute_agent_and_structure(
                agent_executor=sampling_executor,
                agent_config=sampling_config,
                user_input=user_input,
                llm=sampling_llm,
                output_schema=GitLabAnalysis,
                agent_label=f"GitLabAnalyst_Sampling_{i+1}",
            )
            if res and res.story:
                samples.append(res.story)
        except Exception as e:
            logger.error("Gagal mendapatkan sampel ke-%d: %s", i + 1, e)

    # ─── SEMANTIC CLUSTERING & ENTROPY CALCULATION ───
    if len(samples) < 2:
        logger.warning("Jumlah sampel kurang dari 2. Melewati pre-check uncertainty.")
        normalized_score = 0.0
    else:
        logger.info("Menghitung tingkat ketidakpastian (entropy)...")
        embeddings_model = load_embeddings_model()
        clusters = semantic_clustering(samples, embeddings_model, threshold=0.90)
        
        M = len(samples)
        K = len(clusters)
        entropy = 0.0
        
        for cluster in clusters:
            count = len(cluster)
            prob = count / M
            if prob > 0:
                entropy += - (prob * math.log(prob))
                
        max_entropy = math.log(M) if M > 1 else 1.0
        normalized_score = entropy / max_entropy if M > 1 else 0.0
        logger.info(f"Uncertainty Evaluation - Clusters: {K}, Entropy: {entropy:.3f}, Normalized Score: {normalized_score:.3f}")
        
        # Cetak langsung ke terminal agar mudah dilihat pengguna
        status_ragu = "RAGU / UNCERTAIN (Melebihi Threshold)" if normalized_score > 0.400 else "YAKIN / CONFIDENT"
        print(f"\n" + "=" * 50)
        print(f"  [UNCERTAINTY PRE-CHECK REPORT]")
        print(f"  - Jumlah Sampel (M)        : {M}")
        print(f"  - Jumlah Klaster Semantik  : {K}")
        print(f"  - Normalized Entropy Score : {normalized_score:.3f}")
        print(f"  - Status Keyakinan Sistem  : {status_ragu}")
        print(f"==================================================")


    # ─── FASE 2: CONDITIONAL ROUTING ───
    THRESHOLD = 0.400
    if normalized_score > THRESHOLD:
        # KONDISI B: Reject / System is Uncertain
        escalation_msg = (
            f"Halo tim, saya sebagai AI GitLab Analyst menemukan adanya instruksi yang kontradiktif atau ambigu "
            f"Mohon klarifikasi lebih lanjut mengenai requirement fitur atau deskripsi dari fitur ini sebelum saya memprosesnya."
        )
        post_gitlab_comment(project_id, issue_iid, escalation_msg)
        
        raise ValueError(
            f"Analisis ditolak karena tingkat ketidakpastian tinggi ({normalized_score:.3f} > {THRESHOLD}). "
            f"Komentar eskalasi telah dikirim ke GitLab Issue."
        )

    # KONDISI A: Pass / System is Confident (atau sampling dilewati)
    logger.info("Fase 2: Menjalankan eksekusi deterministik (temperature=0.0)...")
    deterministic_llm = create_llm(temperature=0.0, max_tokens=2048)
    deterministic_executor, deterministic_config = create_agent_with_memory(
        llm=deterministic_llm,
        tools=[mock_extract_tool],
        system_prompt=SYSTEM_PROMPT_GITLAB,
        agent_name="GitLabAnalyst",
        thread_id=f"deterministic_{project_id}_{issue_iid}"
    )

    user_input = f"Tolong analisis issue #{issue_iid} pada project {project_id} dan buatkan satu User Story yang merepresentasikan kebutuhan utama dari issue tersebut."
    return execute_agent_and_structure(
        agent_executor=deterministic_executor,
        agent_config=deterministic_config,
        user_input=user_input,
        llm=deterministic_llm,
        output_schema=GitLabAnalysis,
        agent_label="GitLabAnalyst",
    )


if __name__ == "__main__":
    try:
        result = run_gitlab_analyst_agent(project_id="81209841", issue_iid=3)
        print("\n" + "=" * 60)
        print("FINAL STRUCTURED ANALYSIS RESULT")
        print("=" * 60)
        print(result.model_dump_json(indent=4))
        print("=" * 60)
    except Exception as e:
        logger.exception("Fatal error: %s", e)