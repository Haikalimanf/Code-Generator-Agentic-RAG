import logging
from typing import List, Optional

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langchain.agents import create_agent

from src.config.settings import settings
from src.models.schemas import ComplianceAnalysis
from src.utils.llm_factory import create_llm, execute_agent_and_structure

logger = logging.getLogger("pdf_rag_agent")


@tool
def query_company_guidelines(query: str) -> str:
    """
    Cari informasi di dokumen standar perusahaan (PDF) seperti aturan coding,
    arsitektur Android, dan naming conventions.
    """
    if not settings.vector_database_url:
        return "Error: Database vector (VECTOR_DATABASE_URL) tidak dikonfigurasi."

    try:
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_postgres import PGVector

        embeddings = HuggingFaceEmbeddings(
            model_name=settings.rag_embedding_model,
            model_kwargs={"device": "cpu"},
        )

        vectorstore = PGVector(
            embeddings=embeddings,
            collection_name=settings.rag_collection_name,
            connection=settings.vector_database_url,
            use_jsonb=True,
        )

        docs = vectorstore.similarity_search(query, k=4)

        context = ""
        for i, doc in enumerate(docs):
            page = doc.metadata.get("page", "?")
            context += f"\n--- Sumber {i+1} (Hal: {page}) ---\n{doc.page_content}\n"

        return context
    except Exception as e:
        return f"Error saat mengakses database vector: {e}"


SYSTEM_PROMPT_COMPLIANCE = (
    "Anda adalah 'The Compliance Expert', pakar standar teknis dan regulasi internal perusahaan.\n"
    "Tugas Anda adalah memastikan setiap fitur yang dikembangkan mengikuti pedoman (guidelines) "
    "perusahaan yang ada di dalam dokumen PDF.\n\n"
    "ATURAN UTAMA:\n"
    "1. Selalu gunakan tool query_company_guidelines untuk mencari fakta.\n"
    "2. Jika informasi tidak ada di dokumen, katakan bahwa standar spesifik tidak ditemukan.\n"
    "3. Fokus pada: Naming Conventions, Arsitektur Android (MVVM), dan Best Practices Keamanan.\n"
)


def run_compliance_expert_agent(user_query: str, thread_id: str = "rag_default") -> ComplianceAnalysis:
    llm = create_llm(temperature=0.0)
    tools = [query_company_guidelines]

    from src.utils.llm_factory import create_agent_with_memory
    agent_executor, config = create_agent_with_memory(
        llm=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT_COMPLIANCE,
        agent_name="ComplianceExpert",
        thread_id=thread_id,
    )

    return execute_agent_and_structure(
        agent_executor=agent_executor,
        agent_config=config,
        user_input=user_query,
        llm=llm,
        output_schema=ComplianceAnalysis,
        agent_label="ComplianceExpert",
    )


if __name__ == "__main__":
    try:
        query = "Bagaimana standar penamaan (Naming Convention) untuk project Android?"
        result = run_compliance_expert_agent(query)

        print("\n" + "=" * 60)
        print("REPORT: COMPANY COMPLIANCE ANALYSIS")
        print("=" * 60)
        print(result.model_dump_json(indent=4))
        print("=" * 60)

    except Exception as e:
        logger.exception("Fatal error: %s", e)