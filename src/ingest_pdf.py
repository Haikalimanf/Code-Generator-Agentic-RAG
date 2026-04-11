import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

load_dotenv()

connection_string = os.getenv("VECTOR_DATABASE_URL")

if not connection_string:
    raise ValueError("VECTOR_DATABASE_URL tidak ditemukan di file .env")

print("Environment variables loaded.")

# 1. Load PDF
PDF_PATH = "../data/SuitMobile Code Style [Android] - Naming - Version 2.pdf"

print(f"Memuat file {PDF_PATH}...")
loader = PyPDFLoader(PDF_PATH)
docs = loader.load()
print(f"Dokumen berhasil dimuat: {len(docs)} halaman")

# 2. Split text
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=100
)
splits = text_splitter.split_documents(docs)
print(f"Berhasil! Dokumen dipecah menjadi {len(splits)} potongan (chunks).")

# 3. Create Embeddings
print("Memuat model embedding...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)

# 4. Save to Vector Store
COLLECTION_NAME = "permenpan_index_v3"

vectorstore = PGVector(
    embeddings=embeddings,
    collection_name=COLLECTION_NAME,
    connection=connection_string,
    use_jsonb=True,
)

print(f"Menyimpan vector ke tabel '{COLLECTION_NAME}' di Postgres...")
vectorstore.add_documents(splits)
print("Penyimpanan selesai!")
