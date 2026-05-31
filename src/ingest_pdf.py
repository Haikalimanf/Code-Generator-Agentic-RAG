import sys
import logging
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector

from src.config.settings import settings

logger = logging.getLogger("ingest_pdf")

connection_string = settings.vector_database_url

if not connection_string:
    raise ValueError("VECTOR_DATABASE_URL tidak ditemukan di file .env")

DATA_DIR = settings.project_root / "data"

PDF_FILES = [
    "Suitcore Android MVVM Documentation V1.pdf",
    "SuitMobile Code Style [Android] - Naming - Version 2.pdf",
]

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""],
)

all_splits = []
for pdf_name in PDF_FILES:
    pdf_path = DATA_DIR / pdf_name

    if not pdf_path.exists():
        logger.warning("File tidak ditemukan: %s", pdf_path)
        continue

    logger.info("Memuat file: %s...", pdf_name)
    try:
        loader = PyPDFLoader(str(pdf_path))
        docs = loader.load()
        logger.info("Berhasil memuat %d halaman dari %s", len(docs), pdf_name)

        splits = text_splitter.split_documents(docs)

        # Injeksi metadata source agar RAG agent bisa menyebutkan nama dokumen asal
        for split in splits:
            split.metadata["source"] = pdf_name

        logger.info("Dipecah menjadi %d potongan (chunks) dengan metadata source", len(splits))
        all_splits.extend(splits)
    except Exception as e:
        logger.error("Gagal memproses %s: %s", pdf_name, e)

if not all_splits:
    logger.error("Tidak ada dokumen untuk di-ingest.")
    sys.exit(1)

logger.info("Memuat model embedding (%s)...", settings.rag_embedding_model)
embeddings = HuggingFaceEmbeddings(
    model_name=settings.rag_embedding_model,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": False},
)

COLLECTION_NAME = settings.rag_collection_name

logger.info("Menghubungkan ke PostgreSQL Vector Store (Collection: '%s')...", COLLECTION_NAME)
try:
    vectorstore = PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=connection_string,
        use_jsonb=True,
    )

    logger.info("Menyimpan %d chunks ke database...", len(all_splits))
    vectorstore.add_documents(all_splits)
    logger.info("Ingest data selesai!")
except Exception as e:
    logger.error("Terjadi kesalahan saat menyimpan ke database: %s", e)