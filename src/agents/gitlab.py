import sys
import logging
import traceback
from typing import Any

import gitlab
import gitlab.exceptions
from langchain_core.tools import tool

from src.config.settings import settings
from src.models.schemas import GitLabAnalysis
from src.utils.error_handler import wrap_tool_call
from src.utils.llm_factory import create_llm, create_agent_with_memory, execute_agent_and_structure

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


@tool
@wrap_tool_call
def extract_gitlab_issue_specs(project_id: str, issue_iid: int) -> str:
    """
    Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.

    Args:
        project_id: ID dari project GitLab
        issue_iid: Internal ID dari issue
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


def run_gitlab_analyst_agent(project_id: str, issue_iid: int) -> GitLabAnalysis:
    llm = create_llm(temperature=0.0, max_tokens=2048)
    tools = [extract_gitlab_issue_specs]

    agent_executor, config = create_agent_with_memory(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_GITLAB,
        agent_name="GitLabAnalyst",
    )

    user_input = f"Tolong analisis issue #{issue_iid} pada project {project_id} dan buatkan satu User Story yang merepresentasikan kebutuhan utama dari issue tersebut."
    return execute_agent_and_structure(
        agent_executor=agent_executor,
        agent_config=config,
        user_input=user_input,
        llm=llm,
        output_schema=GitLabAnalysis,
        agent_label="GitLabAnalyst",
    )


if __name__ == "__main__":
    try:
        result = run_gitlab_analyst_agent(project_id="81209841", issue_iid=1)
        print("\n" + "=" * 60)
        print("FINAL STRUCTURED ANALYSIS RESULT")
        print("=" * 60)
        print(result.model_dump_json(indent=4))
        print("=" * 60)
    except Exception as e:
        logger.exception("Fatal error: %s", e)