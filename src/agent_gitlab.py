import os
import sys
import warnings
import functools
import traceback
import gitlab
import gitlab.exceptions
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate

# Abaikan warning jika masih muncul dari versi langchain yang berbeda
warnings.filterwarnings("ignore", message=".*create_react_agent.*", category=DeprecationWarning)

load_dotenv()

# ──────────────────────────────────────────────
# 1. Structured Output Schema
# ──────────────────────────────────────────────
class GitLabAnalysis(BaseModel):
    """Skema hasil analisis requirement dari GitLab issue."""
    feature_goal: str = Field(description="Penjelasan singkat tujuan fitur berdasarkan issue.")
    acceptance_criteria: List[str] = Field(description="Daftar poin kriteria keberhasilan yang disebutkan.")
    functional_scope: List[str] = Field(description="Bagian aplikasi atau alur kerja yang terdampak secara fungsional.")
    technical_details: Optional[str] = Field(description="Library, versi, atau teknologi yang disebutkan langsung. Isi 'None' jika tidak ada.")
    questions_ambiguities: List[str] = Field(description="Daftar ketidakjelasan atau informasi yang kurang untuk implementasi.")

# Dekorator kustom untuk menangkap error pada level tool
def wrap_tool_call(func):
    """
    Menangkap semua exception pada tool dan mengembalikannya sebagai string.
    Hal ini mencegah agen dari crash dan memungkinkan LLM untuk mendiagnosis masalah.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = f"Error executing tool '{func.__name__}': {str(e)}"
            print(f"[Tool Error] {error_msg}", file=sys.stderr)
            # Opsional: Sertakan traceback jika dalam mode debug
            # return f"{error_msg}\n{traceback.format_exc()}"
            return error_msg
    return wrapper

# 1. Konfigurasi & Inisialisasi GitLab
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")

def get_gitlab_client():
    """Menginisialisasi dan memvalidasi client GitLab."""
    if not GITLAB_TOKEN:
        raise ValueError("GITLAB_TOKEN tidak ditemukan di environment variable.")
    
    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    try:
        gl.auth()  # Validasi token segera
        return gl
    except gitlab.exceptions.GitlabAuthenticationError:
        raise ConnectionError("Gagal autentikasi ke GitLab. Periksa GITLAB_TOKEN Anda.")
    except Exception as e:
        raise ConnectionError(f"Gagal terhubung ke GitLab: {str(e)}")

@tool
@wrap_tool_call
def extract_gitlab_issue_specs(project_id: str, issue_iid: int) -> str:
    """
    Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.
    Gunakan tool ini ketika Anda diminta untuk menganalisis kebutuhan fitur dari GitLab.
    
    Args:
        project_id: ID dari project GitLab (contoh: '12345678')
        issue_iid: Internal ID dari issue (contoh: 1, 2, 3)
    """
    print(f"[GitLab] Connecting to project {project_id}, issue #{issue_iid}...", file=sys.stderr)
    
    gl = get_gitlab_client()
    
    try:
        project = gl.projects.get(project_id)
        issue = project.issues.get(issue_iid)
        
        desc_size = len(issue.description) if issue.description else 0
        print(f"[GitLab] Fetching issue: '{issue.title}' (Desc size: {desc_size} chars)", file=sys.stderr)
        
        # Ekstraksi Data Utama
        spec_data = {
            "title": issue.title,
            "state": issue.state,
            "labels": issue.labels,
            "description": issue.description,
            "comments": []
        }
        
        # Ekstraksi Komentar (Notes) - Mengabaikan log sistem
        notes = issue.notes.list(all=True)
        for note in notes:
            if not note.system: # Hanya ambil komentar dari manusia/developer
                spec_data["comments"].append({
                    "author": note.author['username'],
                    "body": note.body
                })
        
        comments_count = len(spec_data["comments"])
        comments_size = sum(len(c['body']) for c in spec_data["comments"])
        print(f"[GitLab] Found {comments_count} human comments (Total size: {comments_size} chars)", file=sys.stderr)
                
        # Format ke string agar mudah dibaca oleh LLM
        formatted_spec = (
            f"Fitur/Issue: {spec_data['title']}\n"
            f"Status: {spec_data['state']}\n"
            f"Labels: {', '.join(spec_data['labels'])}\n"
            f"Deskripsi:\n{spec_data['description']}\n\n"
            f"Komentar Diskusi:\n"
        )
        
        for c in spec_data["comments"]:
            formatted_spec += f"- {c['author']}: {c['body']}\n"
            
        print(f"[GitLab] Total Context Size: {len(formatted_spec)} chars", file=sys.stderr)
        return formatted_spec

    except gitlab.exceptions.GitlabGetError as e:
        return f"Error: Project atau Issue tidak ditemukan (HTTP {e.response_code})."
    except Exception as e:
        return f"Terjadi kesalahan tak terduga saat mengambil data GitLab: {str(e)}"

# 2. Inisialisasi Agen (The Analyst)
def run_gitlab_analyst_agent(project_id: str, issue_iid: int) -> GitLabAnalysis:
    # Menggunakan model Instruct yang optimal untuk task ini
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL"),
        temperature=0.0,
        max_tokens=2048,
    )
    
    # Daftarkan tools yang bisa digunakan agen
    tools = [extract_gitlab_issue_specs]
    
    # Instruksi sistem yang lebih grounded (mencegah halusinasi)
    system_instructions = (
        "Anda adalah 'The Analyst', agen ahli dalam mengekstraksi dan merangkum kebutuhan perangkat lunak dari GitLab.\n"
        "Tugas Anda adalah memanggil tool extract_gitlab_issue_specs, membaca hasilnya, dan "
        "merangkumnya menjadi 'Functional Requirements' yang berbasis fakta.\n\n"
        "ATURAN KETAT:\n"
        "1. JANGAN MENGADA-NGADA (Hallucination). Hanya gunakan informasi yang ada di teks issue/komentar.\n"
        "2. Jangan menebak arsitektur teknis, nama class, atau direktori jika tidak disebutkan secara eksplisit.\n"
        "3. Jika ada informasi yang hilang namun krusial, tuliskan pada bagian 'Questions/Ambiguities'.\n\n"
        "Output Anda WAJIB memiliki struktur berikut:\n"
        "1. **Feature Goal**: Penjelasan singkat tujuan fitur berdasarkan issue.\n"
        "2. **Acceptance Criteria**: Daftar poin kriteria keberhasilan yang disebutkan.\n"
        "3. **Explicit Technical Details**: Library, versi, atau teknologi yang disebutkan langsung (Isi 'None' jika tidak ada).\n"
        "4. **Functional Scope**: Bagian aplikasi atau alur kerja yang terdampak secara fungsional.\n"
        "5. **Questions/Ambiguities**: Daftar ketidakjelasan atau informasi yang kurang untuk implementasi.\n\n"
        "Berikan output yang objektif dan berbasis data."
    )
    
    # Buat agen reaktif
    agent_executor = create_agent(llm, tools, system_prompt=system_instructions, name="GitLabAnalyst")
    
    print(f"\n[Analyst Agent] Starting analysis for issue #{issue_iid}...", file=sys.stderr)
    
    # Eksekusi agen dengan input string langsung
    user_input = f"Tolong analisis issue #{issue_iid} pada project {project_id} dan buatkan Requirement Specs."
    
    final_output = ""
    
    # Streaming updates memungkinkan kita melihat status setiap 'node' (langkah) agen secara real-time
    for chunk in agent_executor.stream(
        {"messages": [("human", user_input)]}, 
        stream_mode="updates"
    ):
        for node_name, node_update in chunk.items():
            print(f"[Node: {node_name}] is processing...", file=sys.stderr)
            
            # Jika node memberikan output pesan (biasanya dari 'agent' atau 'tools')
            if "messages" in node_update:
                last_message = node_update["messages"][-1]
                
                # Jika pesan adalah hasil akhir dari asisten
                if hasattr(last_message, 'content') and last_message.content:
                    final_output = last_message.content
                    
    print(f"[Analyst Agent] Analysis complete.", file=sys.stderr)
    
    # Konversi output Markdown dari agen ke Structured Output (Pydantic)
    print(f"[Analyst Agent] Structuring output...", file=sys.stderr)
    llm_structured = llm.with_structured_output(GitLabAnalysis)
    structured_result = llm_structured.invoke(final_output)
    
    return structured_result

if __name__ == "__main__":
    # Contoh penggunaan
    try:
        # Gunakan project_id dan issue_iid yang sesuai
        result = run_gitlab_analyst_agent(project_id="81209841", issue_iid=1)
        
        # Cetak hasil secara rapi (Pretty Print)
        print("\n" + "="*60)
        print("FINAL STRUCTURED ANALYSIS RESULT")
        print("="*60)
        print(result.model_dump_json(indent=4))
        print("="*60)
        
    except Exception as e:
        print(f"\n[Fatal Error] {str(e)}", file=sys.stderr)
        traceback.print_exc()