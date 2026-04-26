import os
import sys
import functools
import traceback
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

load_dotenv()

# ==================== STATE & CONFIG ====================
connection_string = os.getenv("VECTOR_DATABASE_URL")
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME")

# ──────────────────────────────────────────────
# 1. Structured Output Schema
# ──────────────────────────────────────────────
class ComplianceAnalysis(BaseModel):
    """Skema hasil analisis kepatuhan terhadap standar perusahaan."""
    guideline_summary: str = Field(description="Ringkasan pedoman perusahaan yang relevan dengan tugas.")
    standards_applied: List[str] = Field(description="Daftar standar teknis atau arsitektur yang harus diikuti.")
    naming_conventions: List[str] = Field(description="Aturan penamaan (Naming Conventions) yang disebutkan dalam dokumen.")
    relevant_sections: List[str] = Field(description="Bagian atau halaman dokumen yang menjadi referensi.")
    recommendations: Optional[str] = Field(description="Saran perbaikan agar sesuai dengan standar perusahaan.")

# ──────────────────────────────────────────────
# 2. Tool Retrieval
# ──────────────────────────────────────────────

@tool
def query_company_guidelines(query: str) -> str:
    """
    Cari informasi di dokumen standar perusahaan (PDF) seperti aturan coding, 
    arsitektur Android, dan naming conventions.
    """
    if not connection_string:
        return "Error: Database vector (VECTOR_DATABASE_URL) tidak dikonfigurasi."

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_postgres import PGVector

        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'}
        )

        vectorstore = PGVector(
            embeddings=embeddings,
            collection_name="company_guidelines",
            connection=connection_string,
            use_jsonb=True,
        )

        docs = vectorstore.similarity_search(query, k=4)
        
        context = ""
        for i, doc in enumerate(docs):
            page = doc.metadata.get("page", "?")
            context += f"\n--- Sumber {i+1} (Hal: {page}) ---\n{doc.page_content}\n"
        
        return context
    except Exception as e:
        return f"Error saat mengakses database vector: {str(e)}"

# ──────────────────────────────────────────────
# 3. Agent Execution (The Compliance Expert)
# ──────────────────────────────────────────────

def run_compliance_expert_agent(user_query: str, thread_id: str = "rag_default") -> ComplianceAnalysis:
    """
    Menjalankan agen ahli kepatuhan untuk mengecek standar perusahaan.
    """
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0,
    )

    tools = [query_company_guidelines]
    
    system_instructions = (
        "Anda adalah 'The Compliance Expert', pakar standar teknis dan regulasi internal perusahaan.\n"
        "Tugas Anda adalah memastikan setiap fitur yang dikembangkan mengikuti pedoman (guidelines) "
        "perusahaan yang ada di dalam dokumen PDF.\n\n"
        "ATURAN UTAMA:\n"
        "1. Selalu gunakan tool query_company_guidelines untuk mencari fakta.\n"
        "2. Jika informasi tidak ada di dokumen, katakan bahwa standar spesifik tidak ditemukan.\n"
        "3. Fokus pada: Naming Conventions, Arsitektur Android (MVVM), dan Best Practices Keamanan.\n"
    )

    memory = MemorySaver()
    agent_executor = create_agent(llm, tools, system_prompt=system_instructions, checkpointer=memory)

    config = {"configurable": {"thread_id": thread_id}}
    final_output = ""

    print(f"\n[Compliance Expert] Analyzing guidelines for: {user_query[:50]}...", file=sys.stderr)

    for chunk in agent_executor.stream(
        {"messages": [("human", user_query)]},
        config,
        stream_mode="updates"
    ):
        for node_name, node_update in chunk.items():
            print(f"📍 [Node: {node_name}] is processing...", file=sys.stderr)
            if "messages" in node_update:
                last_msg = node_update["messages"][-1]
                if hasattr(last_msg, 'content') and last_msg.content:
                    final_output = last_msg.content

    print(f"✅ [Compliance Expert] Analysis complete.", file=sys.stderr)

    # Konversi ke Structured Output
    print(f"📝 [Compliance Expert] Structuring analysis...", file=sys.stderr)
    llm_structured = llm.with_structured_output(ComplianceAnalysis)
    structured_result = llm_structured.invoke(final_output)

    return structured_result


# ==================== DEMO ONLY - Run when executed directly ====================
if __name__ == "__main__":
    try:
        # Contoh query
        query = "Bagaimana standar penamaan (Naming Convention) untuk project Android?"
        result = run_compliance_expert_agent(query)
        
        print("\n" + "="*60)
        print("📋 COMPANY COMPLIANCE ANALYSIS")
        print("="*60)
        print(result.model_dump_json(indent=4))
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ [Fatal Error] {str(e)}", file=sys.stderr)
        traceback.print_exc()