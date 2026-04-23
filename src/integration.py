"""
CONTOH PRODUKSI: Integrasi GitLab Agent dengan Integration Orchestrator

Flow:
1. GitLab Agent: Menganalisis issue dan membuat technical requirement spec.
2. Integration Orchestrator: Mengambil spec tersebut dan mencari context di Android Studio, Postman, dan RAG.
3. Output: Dokumen context teknis lengkap untuk proses coding selanjutnya.
"""

import asyncio
import json
import warnings
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Filter warnings dari langchain
warnings.filterwarnings("ignore", message=".*create_react_agent.*", category=DeprecationWarning)

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

load_dotenv()

# Konfigurasi LLM
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME")

PROJECT_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_PATH = str(PROJECT_ROOT / "src" / "orchestrator.py")

def get_llm():
    return ChatOpenAI(
        model=MODEL_NAME,
        temperature=0.0,
        api_key=API_KEY,
        base_url=BASE_URL,
        max_tokens=4096,
    )

async def run_full_integration_flow(project_id: str, issue_iid: int):
    """
    Eksekusi flow lengkap dari GitLab sampai Context Retrieval.
    """
    print("\n" + "=" * 60)
    print("      FULL INTEGRATION FLOW START")
    print("=" * 60 + "\n")

    # --- STEP 1: GitLab Analysis ---
    print("[Step 1] Fetching & Analyzing GitLab Issue...")
    try:
        from agent_gitlab import run_gitlab_analyst_agent
        requirement_obj = run_gitlab_analyst_agent(project_id, issue_iid)
        
        # Konversi ke string agar bisa dikirim ke Orchestrator dan dihitung panjangnya
        requirement_spec = requirement_obj.model_dump_json(indent=2)
        print(f"DONE: Requirement Spec Generated ({len(requirement_spec)} chars)")
    except Exception as e:
        print(f"ERR: GitLab Stage Error: {e}")
        return

    # --- STEP 2: Orchestration ---
    print("\n[Step 2] Querying Orchestrator for Technical Context...")
    
    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }
    
    try:
        client = MultiServerMCPClient(orchestrator_config)
        tools = await client.get_tools()
        llm = get_llm()
        agent = create_react_agent(model=llm, tools=tools)
            
        # Buat prompt yang sangat detail untuk Orchestrator
        orchestrator_query = (
            f"Tolong kumpulkan semua konteks teknis yang diperlukan untuk implementasi requirement berikut:\n\n"
            f"{requirement_spec}\n\n"
            f"Instruksi Khusus:\n"
            f"1. Gunakan 'android_studio' untuk mencari file, manifest, dan struktur project.\n"
            f"2. Gunakan 'postman' untuk mencari API contracts jika fitur ini membutuhkan integrasi backend.\n"
            f"3. Gunakan 'rag' untuk mencari pedoman coding perusahaan atau best practices.\n"
            f"4. Gabungkan semua informasi tersebut menjadi satu laporan teknis yang komprehensif."
        )
        
        print("   (Memanggil Brain Orchestrator, harap tunggu...)")
        response = await agent.ainvoke({"messages": [{"role": "user", "content": orchestrator_query}]})
        
        final_context = response["messages"][-1].content
        
        # --- STEP 3: Save to Markdown ---
        output_dir = PROJECT_ROOT / "outputs"
        output_dir.mkdir(exist_ok=True)
        
        filename = f"technical_context_issue_{issue_iid}.md"
        filepath = output_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Technical Context for Issue #{issue_iid}\n\n")
            f.write(final_context)
            
        # --- STEP 4: Final Output ---
        print("\n" + "=" * 60)
        print("      FINAL TECHNICAL CONTEXT")
        print("=" * 60 + "\n")
        print(final_context)
        print("\n" + "=" * 60)
        print(f"✅ SUCCESS: Result saved to {filepath}")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"ERR: Orchestration Stage Error: {e}")

if __name__ == "__main__":
    # Ganti dengan Project ID dan Issue IID Anda
    # Project ID '81209841' adalah contoh project publik
    TEST_PROJECT_ID = "81209841"
    TEST_ISSUE_IID = 1
    
    if len(sys.argv) > 2:
        asyncio.run(run_full_integration_flow(sys.argv[1], int(sys.argv[2])))
    else:
        print(f"INFO: Menggunakan default issue: Project {TEST_PROJECT_ID} Issue #{TEST_ISSUE_IID}")
        asyncio.run(run_full_integration_flow(TEST_PROJECT_ID, TEST_ISSUE_IID))
