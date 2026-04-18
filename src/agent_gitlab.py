import os
from dotenv import load_dotenv
import gitlab
from typing import List, Dict
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage

load_dotenv()

# 1. Konfigurasi Client GitLab
GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.com")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN") # Gunakan Personal Access Token GitLab

@tool
def extract_gitlab_issue_specs(project_id: str, issue_iid: int) -> str:
    """
    Mengambil deskripsi issue, label, dan komentar pengguna dari GitLab.
    Gunakan tool ini ketika Anda diminta untuk menganalisis kebutuhan fitur dari GitLab.
    
    Args:
        project_id: ID dari project GitLab (contoh: '12345678')
        issue_iid: Internal ID dari issue (contoh: 1, 2, 3)
    """
    try:
        gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
        project = gl.projects.get(project_id)
        issue = project.issues.get(issue_iid)
        
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
            
        return formatted_spec

    except Exception as e:
        return f"Error fetching GitLab issue: {str(e)}"

# 2. Inisialisasi Agen (The Analyst)
def run_gitlab_analyst_agent(project_id: str, issue_iid: int) -> str:
    # Menggunakan model Instruct yang optimal untuk task ini
    llm = ChatOpenAI(
        model="anthropic/claude-sonnet-4.5",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL"),
        temperature=0.0,
        max_tokens=2048,
    )
    
    # Daftarkan tools yang bisa digunakan agen
    tools = [extract_gitlab_issue_specs]
    
    # Buat agen reaktif
    agent_executor = create_react_agent(llm, tools)
    
    # Prompt instruksi spesifik untuk Agen 1
    system_prompt = (
        "Anda adalah 'The Analyst', agen ahli dalam menganalisis kebutuhan perangkat lunak. "
        "Tugas Anda adalah memanggil tool extract_gitlab_issue_specs, membaca hasilnya, dan "
        "merangkumnya menjadi 'Requirement Specs' yang bersih dan terstruktur untuk tim developer. "
        "Fokus pada acceptance criteria, constraint arsitektur, dan perubahan yang diminta dalam komentar."
    )
    
    user_prompt = f"Tolong analisis issue #{issue_iid} pada project {project_id} dan buatkan Requirement Specs."
    
    # Eksekusi agen
    messages = [
        {"role": "system", "content": system_prompt},
        HumanMessage(content=user_prompt)
    ]
    
    response = agent_executor.invoke({"messages": messages})
    
    # Mengembalikan pesan terakhir (hasil analisis)
    return response["messages"][-1].content

if __name__ == "__main__":
    result = run_gitlab_analyst_agent(project_id="81209841", issue_iid=1)
    print(result)