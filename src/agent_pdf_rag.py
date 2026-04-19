"""
agent_pdf_rag.py - RAG Chain untuk dokumen perusahaan (PDF → PostgreSQL Vector Store)

Didesain untuk diimport oleh orchestrator.py secara langsung (tanpa MCP Server).
Jika VECTOR_DATABASE_URL tidak tersedia atau DB tidak bisa diakses,
module ini tetap bisa diimport dengan rag_chain = None (graceful degradation).
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ==================== STATE VARIABLES ====================
rag_chain = None
RAG_AVAILABLE = False
RAG_ERROR = None

# ==================== INITIALIZATION ====================
connection_string = os.getenv("VECTOR_DATABASE_URL")
API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4.1")

if not connection_string:
    RAG_ERROR = "VECTOR_DATABASE_URL tidak dikonfigurasi di .env"
    print(f"⚠️  [RAG] {RAG_ERROR}", file=sys.stderr)
else:
    try:
        print("🔄 [RAG] Memuat model embedding...", file=sys.stderr)
        from langchain_huggingface import HuggingFaceEmbeddings
        from langchain_postgres import PGVector
        from langchain_openai import ChatOpenAI
        from langchain_classic.chains import create_retrieval_chain
        from langchain_classic.chains.combine_documents import create_stuff_documents_chain
        from langchain_core.prompts import ChatPromptTemplate

        # Embedding model
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': False}
        )

        COLLECTION_NAME = "company_guidelines"

        # Connect ke PostgreSQL Vector Store
        print(f"🔄 [RAG] Koneksi ke vector store '{COLLECTION_NAME}'...", file=sys.stderr)
        vectorstore = PGVector(
            embeddings=embeddings,
            collection_name=COLLECTION_NAME,
            connection=connection_string,
            use_jsonb=True,
        )

        # LLM untuk RAG
        llm = ChatOpenAI(
            model=MODEL_NAME,
            api_key=API_KEY,
            base_url=BASE_URL,
            temperature=0
        )

        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

        system_prompt = (
            "Anda adalah asisten AI yang membantu menjawab pertanyaan berdasarkan konteks yang diberikan di bawah ini. "
            "Jika jawaban tidak ada di dalam konteks, katakan 'Saya tidak menemukan informasi tersebut di dokumen'. "
            "Jawablah dengan bahasa Indonesia yang jelas.\n\n"
            "Konteks:\n{context}"
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        question_answer_chain = create_stuff_documents_chain(llm, prompt)
        rag_chain = create_retrieval_chain(retriever, question_answer_chain)

        RAG_AVAILABLE = True
        print("✅ [RAG] RAG Chain siap digunakan!", file=sys.stderr)

    except Exception as e:
        RAG_ERROR = str(e)
        RAG_AVAILABLE = False
        rag_chain = None
        print(f"❌ [RAG] Gagal menginisialisasi RAG Chain: {e}", file=sys.stderr)
        import traceback
        print(traceback.format_exc(), file=sys.stderr)


# ==================== DEMO ONLY - Run when executed directly ====================
if __name__ == "__main__":
    if not RAG_AVAILABLE:
        print(f"❌ RAG Chain tidak tersedia: {RAG_ERROR}")
        sys.exit(1)

    query = "apa inti utama dokumen ini?"

    print(f"\nPertanyaan: {query}")
    print("-" * 30)

    response = rag_chain.invoke({"input": query})

    print("JAWABAN AI:")
    print(response["answer"])

    print("\n" + "-" * 30)
    print("Sumber Referensi:")
    for i, doc in enumerate(response["context"]):
        print(f"[{i+1}] Halaman {doc.metadata.get('page', '?')}: {doc.page_content[:1000]}...")