import os
from dotenv import load_dotenv

import sys

load_dotenv()

connection_string = os.getenv("VECTOR_DATABASE_URL")

if not connection_string:
    raise ValueError("VECTOR_DATABASE_URL tidak ditemukan di file .env")

API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_URL = os.getenv("OPENROUTER_BASE_URL")

print("Environment variables loaded.")

from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

print("Memuat model embedding (akan download otomatis jika belum ada)...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)

# Ganti nama collection karena dimensi embedding berbeda dari sebelumnya
COLLECTION_NAME = "permenpan_index_v3" 

vectorstore = PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION_NAME,
    connection=connection_string,
    use_jsonb=True,
)

from langchain_openai import ChatOpenAI
from langchain_classic.chains import create_retrieval_chain
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate

llm = ChatOpenAI(
    model="arcee-ai/trinity-large-preview:free", 
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

print("RAG Chain siap digunakan!")

# ==================== DEMO ONLY - Run when executed directly ====================
if __name__ == "__main__":
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