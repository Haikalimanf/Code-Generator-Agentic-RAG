import os
import sys
from dotenv import load_dotenv
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

load_dotenv()

connection_string = os.getenv("VECTOR_DATABASE_URL")

if not connection_string:
    raise ValueError("VECTOR_DATABASE_URL tidak ditemukan di file .env")

print("Environment variables loaded.")

# 1. Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

# List file yang ingin di-ingest
PDF_FILES = [
    "Suitcore Android MVVM Documentation V1.pdf",
    "SuitMobile Code Style [Android] - Naming - Version 2.pdf"
]

# 2. Load and Split Documents
all_splits = []
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

for pdf_name in PDF_FILES:
    pdf_path = DATA_DIR / pdf_name
    
    if not pdf_path.exists():
        print(f"⚠️ File tidak ditemukan: {pdf_path}")
        continue
        
    print(f"🔄 Memuat file: {pdf_name}...")
    try:
        loader = PyPDFLoader(str(pdf_path))
        docs = loader.load()
        print(f"✅ Berhasil memuat {len(docs)} halaman dari {pdf_name}")
        
        splits = text_splitter.split_documents(docs)
        print(f"✂️ Dipecah menjadi {len(splits)} potongan (chunks)")
        all_splits.extend(splits)
    except Exception as e:
        print(f"❌ Gagal memproses {pdf_name}: {e}")

if not all_splits:
    print("❌ Tidak ada dokumen untuk di-ingest.")
    sys.exit(1)

# 3. Create Embeddings
print("\n🔄 Memuat model embedding (sentence-transformers/all-MiniLM-L6-v2)...")
embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': False}
)

# 4. Ingest to Vector Store
COLLECTION_NAME = "company_guidelines"

print(f"🔄 Menghubungkan ke PostgreSQL Vector Store (Collection: '{COLLECTION_NAME}')...")
try:
    vectorstore = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=connection_string,
        use_jsonb=True,
    )

    print(f"🚀 Menyimpan {len(all_splits)} chunks ke database...")
    vectorstore.add_documents(all_splits)
    print("✨ Ingest data selesai!")
except Exception as e:
    print(f"❌ Terjadi kesalahan saat menyimpan ke database: {e}")
