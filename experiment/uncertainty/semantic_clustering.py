import sys
import os
import re
from pathlib import Path
import json
import math

# Memastikan kita bisa mengimport modul dari folder src/
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# TODO: Import fungsi dari src.ingest_pdf / src.servers.pdf_rag
from langchain_huggingface import HuggingFaceEmbeddings
from src.config.settings import settings
import numpy as np

def load_embeddings_model():
    """
    Memuat model embedding (Sesuai dengan src/servers/pdf_rag.py)
    """
    print(f"Loading embedding model: {settings.rag_embedding_model}...")
    embeddings = HuggingFaceEmbeddings(
        model_name=settings.rag_embedding_model,
        model_kwargs={"device": "cpu"},
    )
    return embeddings

def cosine_similarity(v1, v2):
    """Menghitung cosine similarity secara manual menggunakan numpy"""
    dot_product = np.dot(v1, v2)
    norm_v1 = np.linalg.norm(v1)
    norm_v2 = np.linalg.norm(v2)
    if norm_v1 == 0 or norm_v2 == 0:
        return 0.0
    return dot_product / (norm_v1 * norm_v2)

def extract_goal_benefit(sentence):
    """
    [PERBAIKAN 5] Mengekstrak bagian benefit dengan prioritas pencarian kata kunci tertentu.
    
    Urutan prioritas pencarian:
    1. "so that users can ..."
    3. "so that users ..."
   
    """
    # 1. Cari "so that users can"
    match = re.search(r'so\s+that\s+users\s+can\b', sentence, re.IGNORECASE)
    if match:
        return sentence[match.start():].strip()
        
    # 3. Cari "so that users"
    match = re.search(r'so\s+that\s+users\b', sentence, re.IGNORECASE)
    if match:
        return sentence[match.start():].strip()
        
    return sentence.strip()


def semantic_clustering(sentences, embeddings_model, threshold=0.90):
    """
    Melakukan clustering dengan membandingkan centroid klaster.
    Kalimat dengan similarity >= threshold akan masuk ke klaster yang sama.

    Threshold dikembalikan ke 0.80 (standar) karena preprocessing
    extract_goal_benefit() sudah menghilangkan prefix boilerplate
    yang sebelumnya meng-inflate skor similarity.
    """
    if not sentences:
        return []

    # [PERBAIKAN 3] Pre-processing: ekstrak hanya bagian goal + benefit
    cleaned = [extract_goal_benefit(s) for s in sentences]
    print(f"    Cleaned samples for embedding:")
    for i, c in enumerate(cleaned):
        print(f"      [{i+1}] {c[:80]}...")

    # 2. Vector Embedding: Ekstrak nilai vektornya dari teks yang sudah dibersihkan
    vectors = embeddings_model.embed_documents(cleaned)
    clusters = [] # Berisi list index (int) dari kalimat yang masuk klaster tersebut
    
    # 3. Semantic Clustering
    for i, vec in enumerate(vectors):
        placed = False
        for cluster in clusters:
            # Hitung centroid dari klaster saat ini
            centroid = np.mean([vectors[idx] for idx in cluster], axis=0)
            sim = cosine_similarity(vec, centroid)
            
            if sim >= threshold:
                cluster.append(i)
                placed = True
                break
                
        if not placed:
            clusters.append([i])
            
    return clusters

def process_file(input_filename, embeddings_model):
    """
    Membaca file JSON dari folder response_v2/, menghitung entropy & clustering,
    lalu menyimpan ke folder result_v2/ (run baru, tidak menimpa hasil lama).
    """
    base_dir = Path(__file__).parent
    # Baca dari response_v2/ (hasil generate_responses.py terbaru)
    input_path = base_dir / "response" / input_filename
    output_dir = base_dir / "result"
    output_dir.mkdir(parents=True, exist_ok=True)  # Buat folder jika belum ada
    output_path = output_dir / f"scored_{input_filename}"
    
    if not input_path.exists():
        print(f"File {input_filename} tidak ditemukan. Melewati.")
        return
        
    print(f"[{input_filename}] Mulai memproses clustering dan entropy...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    scored_data = []
    
    # 1. Looping Data JSON
    for item in data:
        responses = item.get("sampled_responses", [])
        
        # Ambil sampel yang valid saja
        valid_responses = [r for r in responses if r != "ERROR_GENERATING"]
        M = len(valid_responses)
        
        if M == 0:
            continue
            
        # Panggil fungsi Semantic Clustering (threshold=0.80, preprocessing aktif)
        clusters = semantic_clustering(valid_responses, embeddings_model, threshold=0.90)
        
        K = len(clusters)
        cluster_distribution = []
        entropy = 0.0
        
        # 4. Hitung Probabilitas Klaster
        for idx, cluster in enumerate(clusters):
            count = len(cluster)
            prob = count / M
            
            cluster_distribution.append({
                "cluster_id": idx + 1,
                "count": count,
                "probability": round(prob, 3)
            })
            
            # 5. Hitung Discrete Semantic Entropy (Rumus U)
            if prob > 0:
                entropy += - (prob * math.log(prob))
                
        # 5. Hitung Normalized Shannon Entropy
        # ln(M) adalah nilai Entropi Maksimal (H_max) jika semua kalimat beda klaster
        max_entropy = math.log(M) if M > 1 else 1.0
        normalized_score = entropy / max_entropy if M > 1 else 0.0
        
        # 6. Simpan ke JSON output format
        result_item = {
            "id_test_case": item.get("id_user_story", item.get("id_data")),
            "uncertainty_type": item.get("uncertainty_type", "Unknown"),
            "original_issue_title": item.get("original_issue_title", ""),
            "total_clusters": K,
            "clusters_distribution": cluster_distribution,
            "discrete_semantic_entropy": round(entropy, 3),
            "normalized_uncertainty_score": round(normalized_score, 3)
        }
        scored_data.append(result_item)
        
    # Dump hasil kalkulasi ke file output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(scored_data, f, indent=4, ensure_ascii=False)
        
    print(f"[{input_filename}] Selesai. Disimpan di {output_path.name}\n")

if __name__ == "__main__":
    # Load model ke memori 1x di awal agar proses lebih cepat
    embeddings_model = load_embeddings_model()
    
    # File di-ambil dari folder response/ (hasil generate_responses.py)
    datasets = [
        "responses_aleatoric_data.json",
        "responses_clear_data.json"
    ]
    
    for ds in datasets:
        process_file(ds, embeddings_model)
