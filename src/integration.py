"""
CONTOH PRODUKSI: Integrasi GitLab Agent dengan Integration Orchestrator

Flow:
1. GitLab Agent: Menganalisis issue dan membuat technical requirement spec.
2. Integration Orchestrator: Mengambil spec tersebut dan mencari context di Android Studio, Postman, Figma, dan RAG.
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

load_dotenv()

# Konfigurasi LLM
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME")

PROJECT_ROOT = Path(__file__).parent.parent
ORCHESTRATOR_PATH = str(PROJECT_ROOT / "src" / "orchestrator.py")


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
        print("   Menginisialisasi koneksi ke Orchestrator...")
        client = MultiServerMCPClient(orchestrator_config)
        tools = await client.get_tools()
        
        if not tools:
            print("ERR: Orchestrator tidak mengembalikan tools. Periksa orchestrator.py.")
            return

        print(f"   Tools tersedia: {[t.name for t in tools]}")
        
        # Temukan tool utama secara langsung — TANPA ReAct agent loop
        # create_react_agent tidak perlu di sini karena kita tahu persis tool yang akan dipanggil.
        # Menggunakan agent hanya akan memboroskan token untuk "reasoning" yang tidak perlu.
        integration_tool = next(
            (t for t in tools if t.name == "get_complete_integration_context"), None
        )
        
        if not integration_tool:
            print("ERR: Tool 'get_complete_integration_context' tidak ditemukan di Orchestrator.")
            return
        
        print("   Memanggil Orchestrator tool secara langsung (no agent loop)...")
        print("   [Android Studio + Postman + RAG berjalan paralel, harap tunggu...]")
        
        # Panggil tool langsung dengan timeout 10 menit
        try:
            async with asyncio.timeout(600):
                raw_result = await integration_tool.ainvoke({
                    "requirement": requirement_spec,
                    "include_api": True,
                    "include_design": False,      # Figma dinonaktifkan sementara (butuh Desktop App)
                    "include_kotlin_docs": False,
                    "include_company_guidelines": True,
                })
        except asyncio.TimeoutError:
            print("ERR: Orchestrator timeout (>10 menit). Periksa koneksi ke sub-agents.")
            return
        
        # raw_result bisa berupa string JSON atau string biasa
        try:
            parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            # Buat final context yang rapi dari JSON
            sections = []
            if parsed.get("code_structure"):
                sections.append(f"## 1. Struktur & File Project (Android Studio)\n\n{parsed['code_structure']}")
            if parsed.get("api_contracts"):
                sections.append(f"## 2. API Contracts (Postman)\n\n{parsed['api_contracts']}")
            if parsed.get("design_context"):
                sections.append(f"## 3. Desain UI & XML (Figma)\n\n{parsed['design_context']}")
            if parsed.get("company_guidelines"):
                sections.append(f"## 4. Pedoman Coding & Best Practices (RAG)\n\n{parsed['company_guidelines']}")
            if parsed.get("errors"):
                sections.append(f"## ⚠ Errors & Peringatan\n\n" + "\n".join(f"- {e}" for e in parsed["errors"]))
            final_context = "\n\n---\n\n".join(sections) if sections else str(raw_result)
        except (json.JSONDecodeError, AttributeError):
            final_context = str(raw_result)
        
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
