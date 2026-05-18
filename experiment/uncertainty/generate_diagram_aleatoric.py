import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

BASE_DIR = os.path.join("experiment", "uncertainty", "result")
FILE_PATH = os.path.join(BASE_DIR, "scored_responses_aleatoric_data.json")
OUTPUT_PATH = os.path.join(BASE_DIR, "distribusi_aleatoric_data_histogram.png")

def load_scores(filepath: str, label: str) -> pd.DataFrame:
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

df = load_scores(FILE_PATH, "Aleatoric Data")

if df.empty:
    print("[ERROR] Tidak ada data untuk divisualisasikan.")
    exit(1)

print("\n=== Statistik Ringkas ===")
print(df["score"].describe().to_string())
print()

PALETTE = {"Aleatoric Data": "#e67e22"}
CUSTOM_BINS = [i * 0.1 for i in range(12)]

sns.set_theme(style="whitegrid", font_scale=1.1)
fig, ax = plt.subplots(figsize=(14, 7))

hist = sns.histplot(
    data=df,
    x="score",
    hue="type",
    bins=CUSTOM_BINS,
    palette=PALETTE,
    alpha=0.85,
    edgecolor="white",
    linewidth=0.8,
    ax=ax,
    legend=False
)

for patch in ax.patches:
    height = patch.get_height()
    if height > 0:
        ax.annotate(
            f"{int(height)}",
            xy=(patch.get_x() + patch.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center", va="bottom",
            fontsize=10, fontweight="bold", color="#2c3e50"
        )

ax.set_xlim(-0.05, 1.05)
ax.set_ylim(bottom=0)

y_max = ax.get_ylim()[1]
ax.set_ylim(0, y_max * 1.18)

ax.set_title(
    "Distribusi Normalized Shannon Entropy - Aleatoric Data",
    fontsize=16, fontweight="bold", pad=18
)
ax.set_xlabel("Uncertainty Score (Normalized)", fontsize=13)
ax.set_ylabel("Jumlah Data (Count)", fontsize=13)

tick_positions = [i * 0.1 for i in range(11)]
tick_labels = [f"{x:.1f}" for x in tick_positions]
ax.set_xticks(tick_positions)
ax.set_xticklabels(tick_labels, rotation=0, fontsize=11)

plt.tight_layout()
plt.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
print(f"[OK] Grafik disimpan di: {OUTPUT_PATH}")
