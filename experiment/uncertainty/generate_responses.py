import sys
import os
from pathlib import Path
import json
import time
from typing import Any, Dict

# Memastikan kita bisa mengimport modul dari folder src/
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from src.utils.llm_factory import create_agent_with_memory, execute_agent_and_structure
from src.models.schemas import GitLabAnalysis
from dotenv import load_dotenv

# Muat variabel environment dari file .env di root project
load_dotenv(PROJECT_ROOT / ".env")


def create_openrouter_llm(temperature: float = 1.0, max_tokens: int = 1200) -> ChatOpenAI:
    """
    Membuat instance LLM menggunakan OpenRouter.
    Membaca konfigurasi dari environment variable:
      - OPENROUTER_API_KEY
      - OPENROUTER_BASE_URL
      - WORKER_MODEL_NAME
    """
    api_key      = os.getenv("OPENROUTER_API_KEY", "")
    base_url     = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model_name   = os.getenv("WORKER_MODEL_NAME", "openai/gpt-4o-mini")

    if not api_key:
        raise ValueError(
            "Konfigurasi OpenRouter tidak lengkap. "
            "Pastikan OPENROUTER_API_KEY sudah diset di file .env"
        )

    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )

# ─────────────────────────────────────────────────────────────────────────────
# [PERBAIKAN 1] System Prompt Khusus Eksperimen Uncertainty
#
# MENGAPA DIGANTI?
# SYSTEM_PROMPT_GITLAB yang asli secara eksplisit memerintahkan LLM untuk
# "Pilih SATU aktor utama dan SATU tujuan inti". Instruksi ini menyebabkan
# LLM selalu menghasilkan 5 respons dengan makna yang hampir identik, sehingga
# semua sampel masuk ke 1 klaster dan uncertainty score = 0.
#
# Prompt baru ini membiarkan LLM mengeksplorasi interpretasi yang berbeda
# secara bebas, sesuai dengan ambiguitas yang ada di dalam issue_comments.
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT_EXPERIMENT = (
    "Anda adalah analis kebutuhan perangkat lunak yang sedang melakukan sesi brainstorming. "
    "Tugas Anda adalah membaca deskripsi issue dan komentar diskusi tim, "
    "lalu menulis SATU User Story yang Anda anggap paling masuk akal berdasarkan konteks yang ada.\n\n"

    "ATURAN PENTING:\n"
    "1. Panggil tool extract_gitlab_issue_specs untuk mendapatkan data issue.\n"
    "2. Jika terdapat ambiguitas atau konflik interpretasi dalam komentar, "
    "pilih SALAH SATU interpretasi yang paling Anda yakini benar — jangan menyebutkan konfliknya.\n"
    "3. User story ditulis dari sudut pandang 'mobile developer'.\n"
    "4. Format wajib: 'As a mobile developer, I want [goal], so that [benefit].'\n"
    "5. Tetap ringkas: maksimal 2 kalimat untuk bagian goal dan benefit.\n\n"

    "Berikan output langsung sebagai satu User Story tanpa penjelasan tambahan."
)

# Variabel global untuk mensimulasikan respons dari GitLab API (Dummy Data)
CURRENT_ISSUE_CONTEXT = ""

@tool
def extract_gitlab_issue_specs(project_id: str, issue_iid: int) -> str:
    """
    Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.
    (Di-mock untuk mengembalikan data lokal).
    """
    global CURRENT_ISSUE_CONTEXT
    return CURRENT_ISSUE_CONTEXT

def generate_user_story(issue: Dict[str, Any], thread_id: str) -> str:
    """
    Memanggil agen LLM menggunakan setup dari gitlab agent (SYSTEM_PROMPT_GITLAB),
    tetapi dengan temperatur = 1.0 untuk variasi hasil (eksperimen).
    """
    global CURRENT_ISSUE_CONTEXT
    
    title = issue.get("issue_title", "")
    desc = issue.get("issue_description", "")
    comments = issue.get("issue_comments", [])
    
    # Memformat teks sama seperti output fungsi tool GitLab aslinya
    formatted_spec = f"Fitur/Issue: {title}\nStatus: opened\nLabels: \nDeskripsi:\n{desc}\n\nKomentar Diskusi:\n"
    for c in comments:
        formatted_spec += f"- {c}\n"
        
    # Simpan di context global agar tool agent bisa mengembalikannya
    CURRENT_ISSUE_CONTEXT = formatted_spec
    
    # Inisialisasi LLM via OpenRouter (temperature=1.0 untuk variasi, max_tokens=1200)
    llm = create_openrouter_llm(temperature=1.0, max_tokens=1200)
    tools = [extract_gitlab_issue_specs]
    
    # Buat agent dengan prompt eksperimen (bukan SYSTEM_PROMPT_GITLAB yang asli)
    agent_executor, config = create_agent_with_memory(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_EXPERIMENT,
        agent_name="GitLabAnalyst_Experiment",
        thread_id=thread_id
    )
    
    user_input = f"Tolong analisis issue #{issue.get('id_data')} pada project dummy dan buatkan satu User Story yang merepresentasikan kebutuhan utama dari issue tersebut."
    
    # Jalankan agent dan ubah ke output terstruktur Pydantic (GitLabAnalysis)
    result: GitLabAnalysis = execute_agent_and_structure(
        agent_executor=agent_executor,
        agent_config=config,
        user_input=user_input,
        llm=llm,
        output_schema=GitLabAnalysis,
        agent_label="GitLabAnalyst_Experiment",
    )
    
    # Ambil field 'story'
    return result.story

def process_dataset(input_filename: str):
    """
    Membaca dataset, melooping setiap issue, men-generate 5 sampel, 
    dan menyimpan hasilnya (checkpointing).
    """
    base_dir = Path(__file__).parent
    # Baca dari folder data/, simpan ke folder response_v2/ (run baru, tidak membaca checkpoint lama)
    input_path = base_dir / "data" / input_filename
    output_dir = base_dir / "response"
    output_dir.mkdir(parents=True, exist_ok=True)  # Buat folder jika belum ada
    output_path = output_dir / f"responses_{input_filename}"
    
    print(f"[{input_filename}] Mulai memproses data...")
    
    if not input_path.exists():
        print(f"File {input_filename} tidak ditemukan, lewati.")
        return
        
    with open(input_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    # Load checkpoint jika sebelumnya terputus
    results = []
    if output_path.exists():
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                results = json.load(f)
        except json.JSONDecodeError:
            results = []
            
    processed_ids = {r["id_user_story"] for r in results}
    
    uncertainty_type_map = {
        "clear_data.json": "Clear Contextual",
        "aleatoric_data.json": "Aleatoric Uncertainty",
        "epistemic_data.json": "Epistemic Uncertainty"
    }
    u_type = uncertainty_type_map.get(input_filename, "Unknown")
    
    for issue in dataset:
        issue_id = issue.get("id_data")
        us_id = f"US{issue_id}"
        
        if us_id in processed_ids:
            print(f"Issue {issue_id} sudah diproses, melewati.")
            continue
            
        print(f"[{input_filename}] Memproses Issue {issue_id}: {issue.get('issue_title')}")
        
        sampled_responses = []
        for i in range(5):  # M = 5 sampling untuk uncertainty
            success = False
            retries = 3
            while not success and retries > 0:
                try:
                    # Thread ID dibedakan agar history percakapan agen tidak bertumpuk antar percobaan
                    thread_id = f"exp_{input_filename}_{issue_id}_samp_{i}"
                    story = generate_user_story(issue, thread_id)
                    sampled_responses.append(story)
                    success = True
                    print(f"  -> Sampel {i+1} berhasil di-generate.")
                except Exception as e:
                    retries -= 1
                    print(f"  -> Error saat generate sampel {i+1}: {e}. Retries sisa: {retries}")
                    time.sleep(3)
                    
            if not success:
                print(f"  -> Gagal men-generate sampel {i+1} setelah retry maksimal.")
                sampled_responses.append("ERROR_GENERATING")
                
        # Format ke bentuk JSON Output yang diharapkan
        output_data = {
            "id_user_story": us_id,
            "uncertainty_type": u_type,
            "original_issue_title": issue.get("issue_title"),
            "sampled_responses": sampled_responses
        }
        
        results.append(output_data)
        
        # Simpan ke disk secara berkala (Checkpointing)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
            
        print(f"[{input_filename}] Checkpoint Issue {issue_id} berhasil disimpan.\n")
        
    print(f"[{input_filename}] Selesai diproses sepenuhnya.\n")

if __name__ == "__main__":
    # Jalankan proses pada aleatoric_data.json dan clear_data.json
    datasets = ["clear_data.json"]
    for ds in datasets:
        process_dataset(ds)
