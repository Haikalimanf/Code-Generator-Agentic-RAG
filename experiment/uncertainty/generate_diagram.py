"""
generate_diagram.py
-------------------
Skrip visualisasi distribusi Normalized Shannon Entropy (Uncertainty Score)
untuk keperluan eksperimen Skripsi - Uncertainty Quantification pada Multi-Agent.

Cara menjalankan:
    python experiment/uncertainty/generate_diagram.py
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns


# ─────────────────────────────────────────────────────────────────────────────
# 1. Definisikan path ke 3 file JSON input (relatif terhadap root project)
# ─────────────────────────────────────────────────────────────────────────────
# [DIUPDATE] Membaca dari result_v2/ yang dihasilkan pipeline terbaru (threshold=0.98)
BASE_DIR = os.path.join("experiment", "uncertainty", "result")

FILES = {
    "Clear Data":     os.path.join(BASE_DIR, "scored_responses_clear_data.json"),
    "Aleatoric Data": os.path.join(BASE_DIR, "scored_responses_aleatoric_data.json"),
}

OUTPUT_PATH = os.path.join(BASE_DIR, "distribusi_uncertainty_score_histogram.png")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Fungsi membaca JSON dan mengekstrak list normalized_uncertainty_score
# ─────────────────────────────────────────────────────────────────────────────
def load_scores(filepath: str, label: str) -> pd.DataFrame:
    """
    Membaca file JSON dan mengekstrak nilai 'normalized_uncertainty_score'
    dari setiap item, lalu mengembalikannya sebagai DataFrame.
    """
    scores = []
    if not os.path.exists(filepath):
        print(f"[PERINGATAN] File tidak ditemukan: {filepath}")
        return pd.DataFrame({"score": [], "type": []})

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        score = item.get("normalized_uncertainty_score")
        if score is not None:
            scores.append(score)

    print(f"[{label}] Loaded {len(scores)} data points dari {os.path.basename(filepath)}")
    return pd.DataFrame({"score": scores, "type": label})


# ─────────────────────────────────────────────────────────────────────────────
# 3. Load dan gabungkan semua data ke dalam satu DataFrame
# ─────────────────────────────────────────────────────────────────────────────
df_all = pd.concat(
    [load_scores(path, label) for label, path in FILES.items()],
    ignore_index=True
)

if df_all.empty:
    print("[ERROR] Tidak ada data untuk divisualisasikan. Pastikan file JSON sudah ada di folder result/")
    exit(1)

# Tampilkan statistik ringkas per kelompok
print("\n=== Statistik Ringkas ===")
print(df_all.groupby("type")["score"].describe().to_string())
print()


# ─────────────────────────────────────────────────────────────────────────────
# 4. Visualisasi menggunakan Seaborn KDE Plot
# ─────────────────────────────────────────────────────────────────────────────

PALETTE = {
    "Clear Data":     "#2ecc71",
    "Aleatoric Data": "#e67e22",
}

THRESHOLD = 0.300
# Jumlah bin histogram untuk menempatkan setiap batang tepat di tengah-tengah nilai 0.0, 0.1, ..., 1.0
CUSTOM_BINS = [-0.05 + i * 0.1 for i in range(12)]

sns.set_theme(style="whitegrid", font_scale=1.1)
fig, ax = plt.subplots(figsize=(14, 7))

# Plot histogram batang berdampingan (dodge) agar tiap kelompok tidak saling tumpuk
hist = sns.histplot(
    data=df_all,
    x="score",
    hue="type",
    bins=CUSTOM_BINS,
    multiple="dodge",   # batang tiap kelompok berdampingan, tidak tumpuk
    palette=PALETTE,
    alpha=0.85,
    shrink=0.85,        # jarak antar kelompok batang
    edgecolor="white",
    linewidth=0.8,
    ax=ax,
)

# ─── Anotasi jumlah data (count) di ujung atas tiap batang ───
for patch in ax.patches:
    height = patch.get_height()
    if height > 0:  # hanya tampilkan jika ada isinya
        ax.annotate(
            f"{int(height)}",
            xy=(patch.get_x() + patch.get_width() / 2, height),
            xytext=(0, 4),          # offset 4pt ke atas dari ujung batang
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=9, fontweight="bold", color="#2c3e50"
        )

# Batasi sumbu X dan berikan ruang atas untuk label count
ax.set_xlim(-0.05, 1.05)
ax.set_ylim(bottom=0)

# Tambahkan ruang di atas agar label count tidak terpotong
y_max = ax.get_ylim()[1]
ax.set_ylim(0, y_max * 1.18)

# ─── Bayangan latar "SYSTEM IS CONFIDENT" (kiri threshold) ───
ax.axvspan(0.0, THRESHOLD, color="#2ecc71", alpha=0.07)
ax.text(
    THRESHOLD / 2, y_max * 0.93,
    "SYSTEM IS CONFIDENT",
    color="#27ae60", fontsize=13, fontweight="bold",
    ha="center", va="top", alpha=0.85
)

# ─── Bayangan latar "SYSTEM IS UNCERTAIN" (kanan threshold) ───
ax.axvspan(THRESHOLD, 1.0, color="#e74c3c", alpha=0.07)
ax.text(
    (1.0 + THRESHOLD) / 2, y_max * 0.93,
    "SYSTEM IS UNCERTAIN",
    color="#c0392b", fontsize=13, fontweight="bold",
    ha="center", va="top", alpha=0.85
)

# ─── Garis vertikal Clarification Threshold ───
ax.axvline(x=THRESHOLD, color="black", linestyle="--", linewidth=2.2, zorder=5)
ax.text(
    THRESHOLD + 0.012, y_max * 0.78,
    f"Clarification Threshold\n(τ = {THRESHOLD})",
    color="black", fontsize=10.5, fontweight="bold",
    bbox=dict(facecolor="white", alpha=0.92, edgecolor="#7f8c8d", boxstyle="round,pad=0.5")
)

# ─── Label & Judul ───
ax.set_title(
    "Distribusi Normalized Shannon Entropy (Uncertainty Score)",
    fontsize=16, fontweight="bold", pad=18
)
ax.set_xlabel("Uncertainty Score (Normalized)", fontsize=13)
ax.set_ylabel("Jumlah Data (Count)", fontsize=13)

# Tambahkan label tick X yang informatif dengan 1 nilai tepat (0.0, 0.1, dst)
bin_centers = [i * 0.1 for i in range(11)]
bin_labels = [f"{x:.1f}" for x in bin_centers]
ax.set_xticks(bin_centers)
ax.set_xticklabels(bin_labels, rotation=0, fontsize=11)

# ─── Legend ───
legend = ax.get_legend()
if legend:
    legend.set_title("Kelompok Data")
    legend.set_frame_on(True)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Simpan grafik (tanpa memanggil plt.show() karena blocking di non-GUI environment)
# ─────────────────────────────────────────────────────────────────────────────
plt.tight_layout()
plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
print(f"[OK] Grafik disimpan di: {OUTPUT_PATH}")

