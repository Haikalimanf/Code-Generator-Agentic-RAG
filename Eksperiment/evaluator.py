import json
import os
import pandas as pd
from typing import List
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

load_dotenv()

# Konfigurasi Evaluator
EVAL_MODEL = "openai/gpt-4o-mini"
llm = ChatOpenAI(
    model=EVAL_MODEL,
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url=os.getenv("OPENROUTER_BASE_URL"),
    temperature=0
)

JUDGE_PROMPT = """
Tugas Anda adalah membandingkan dua daftar kebutuhan perangkat lunak: 'Ground Truth' dan 'Prediction'.
Tentukan apakah makna item di Ground Truth berhasil ditangkap oleh Prediction.

Format output Anda WAJIB JSON:
{
  "evaluations": [
    {"requirement": "...", "found": true/false},
    ...
  ],
  "hallucinations_count": 0
}
"""

def calculate_metrics_from_stats(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0
    return precision, recall, f1, accuracy

def evaluate_files():
    response_dir = "Eksperiment/response"
    files = sorted([f for f in os.listdir(response_dir) if f.startswith("results_parameter") and f.endswith(".json")])
    
    final_rows = []
    category_map = {
        "Ideal": "Ideal (Bersih)",
        "Standard": "Standard (Typo/Mix)",
        "Complex": "Complex (Implisit)"
    }

    for filename in files:
        temp_str = filename.replace("results_parameter(", "").replace(").json", "")
        filepath = os.path.join(response_dir, filename)
        
        print(f"\nEvaluating {filename} (Temp {temp_str})...")
        
        with open(filepath, "r", encoding="utf-8") as f:
            results = json.load(f)

        # List untuk menampung stats per baris
        temp_stats = []
        for res in results:
            gt_items = res["ground_truth"]["acceptance_criteria"]
            pred_items = res["prediction"]["acceptance_criteria"] if res["prediction"] else []
            
            tp, fp, fn = 0, 0, 0
            if not pred_items:
                fn = len(gt_items)
            else:
                input_text = f"Ground Truth: {json.dumps(gt_items)}\nPrediction: {json.dumps(pred_items)}"
                try:
                    response = llm.invoke([SystemMessage(content=JUDGE_PROMPT), HumanMessage(content=input_text)])
                    content = response.content.replace("```json", "").replace("```", "").strip()
                    eval_data = json.loads(content)
                    tp = sum(1 for e in eval_data["evaluations"] if e["found"])
                    fn = sum(1 for e in eval_data["evaluations"] if not e["found"])
                    fp = eval_data.get("hallucinations_count", 0)
                except Exception as e:
                    print(f"Error evaluating {filename} Case {res['test_case_id']}: {e}")

            temp_stats.append({
                "category": res["category"],
                "tp": tp, "fp": fp, "fn": fn,
                "latency": res["latency"],
                "valid": res["is_valid_format"]
            })

        df_temp = pd.DataFrame(temp_stats)
        
        # 1. Agregasi per Kategori
        for cat_key, cat_name in category_map.items():
            cat_df = df_temp[df_temp['category'] == cat_key]
            if cat_df.empty: continue
            
            tp_sum = cat_df['tp'].sum()
            fp_sum = cat_df['fp'].sum()
            fn_sum = cat_df['fn'].sum()
            p, r, f1, acc = calculate_metrics_from_stats(tp_sum, fp_sum, fn_sum)
            
            final_rows.append({
                "Temperature": temp_str,
                "Kategori": cat_name,
                "Jumlah Data": len(cat_df),
                "Format Mengikuti Pydantic": f"{cat_df['valid'].mean()*100:.0f}%",
                "Avg. Latency (s)": f"{cat_df['latency'].mean():.2f}",
                "Precision": f"{p:.6f}",
                "Recall": f"{r:.6f}",
                "F1-Score": f"{f1:.6f}",
                "Accuracy": f"{acc:.6f}"
            })

        # 2. Baris TOTAL (Result) untuk suhu ini
        tp_total = df_temp['tp'].sum()
        fp_total = df_temp['fp'].sum()
        fn_total = df_temp['fn'].sum()
        p, r, f1, acc = calculate_metrics_from_stats(tp_total, fp_total, fn_total)
        
        final_rows.append({
            "Temperature": "Result",
            "Kategori": "",
            "Jumlah Data": len(df_temp),
            "Format Mengikuti Pydantic": f"{df_temp['valid'].mean()*100:.0f}%",
            "Avg. Latency (s)": f"{df_temp['latency'].mean():.2f}",
            "Precision": f"{p:.6f}",
            "Recall": f"{r:.6f}",
            "F1-Score": f"{f1:.6f}",
            "Accuracy": f"{acc:.6f}"
        })

    # Final Summary Table
    df_final = pd.DataFrame(final_rows)
    print("\n" + "="*100)
    print("DETAILED METRIC SUMMARY (GROUPED BY CATEGORY)")
    print("="*100)
    print(df_final.to_string(index=False))
    print("="*100)
    
    # Save to CSV
    output_csv = os.path.join(response_dir, "metric_summary_comparison.csv")
    df_final.to_csv(output_csv, index=False)
    print(f"\nSummary table saved to {output_csv}")

if __name__ == "__main__":
    evaluate_files()
