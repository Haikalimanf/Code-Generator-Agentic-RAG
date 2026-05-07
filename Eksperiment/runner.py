import os
import json
import time
import asyncio
from typing import List, Optional
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.callbacks import get_openai_callback
from tqdm import tqdm

# 1. Load Environment
load_dotenv()

# 2. Schema Definition (Matching agent_gitlab.py)
class GitLabAnalysis(BaseModel):
    feature_goal: str = Field(description="Penjelasan singkat tujuan fitur berdasarkan issue.")
    acceptance_criteria: List[str] = Field(description="Daftar poin kriteria keberhasilan yang disebutkan.")
    functional_scope: List[str] = Field(description="Bagian aplikasi atau alur kerja yang terdampak secara fungsional.")
    technical_details: Optional[str] = Field(description="Library, versi, atau teknologi yang disebutkan langsung. Isi 'None' jika tidak ada.")
    questions_ambiguities: List[str] = Field(description="Daftar ketidakjelasan atau informasi yang kurang untuk implementasi.")

# 3. Prompt Template
SYSTEM_INSTRUCTIONS = (
    "Anda adalah 'The Analyst', agen ahli dalam mengekstraksi dan merangkum kebutuhan perangkat lunak dari GitLab.\n"
    "Tugas Anda adalah membaca input yang diberikan dan merangkumnya menjadi 'Functional Requirements' yang berbasis fakta.\n\n"
    "ATURAN KETAT:\n"
    "1. JANGAN MENGADA-NGADA (Hallucination). Hanya gunakan informasi yang ada di teks issue/komentar.\n"
    "2. Jangan menebak arsitektur teknis, nama class, atau direktori jika tidak disebutkan secara eksplisit.\n"
    "3. Jika ada informasi yang hilang namun krusial, tuliskan pada bagian 'Questions/Ambiguities'.\n\n"
    "Output Anda WAJIB memiliki struktur JSON yang valid sesuai skema yang diminta."
)

async def run_experiment():
    dataset_path = "Eksperiment/gitlab_testcase.json"
    output_dir = "Eksperiment/response"
    os.makedirs(output_dir, exist_ok=True)
    
    # Suhu yang diminta user
    temperatures = [0, 0.25, 1.25, 1.50]
    
    # Load Dataset
    with open(dataset_path, "r", encoding="utf-8") as f:
        full_dataset = json.load(f)
    
    # Filter 10 items (3 Ideal, 4 Standard, 3 Complex)
    ideal_items = [tc for tc in full_dataset if tc["category"] == "Ideal"][:3]
    standard_items = [tc for tc in full_dataset if tc["category"] == "Standard"][:4]
    complex_items = [tc for tc in full_dataset if tc["category"] == "Complex"][:3]
    dataset = ideal_items + standard_items + complex_items
    
    for temp in temperatures:
        print(f"\nRunning Experiment for Temperature: {temp}")
        results = []
        
        with get_openai_callback() as cb:
            for tc in tqdm(dataset, desc=f"Temp {temp}"):
                tc_id = tc["id"]
                category = tc["category"]
                ground_truth = tc["ground_truth"]
                spec_data = tc["spec_data"]
                
                formatted_input = (
                    f"Fitur/Issue: {spec_data['title']}\n"
                    f"Status: {spec_data['state']}\n"
                    f"Labels: {', '.join(spec_data['labels'])}\n"
                    f"Deskripsi:\n{spec_data['description']}\n\n"
                    f"Komentar Diskusi:\n"
                )
                for c in spec_data.get("comments", []):
                    formatted_input += f"- {c['author']}: {c['body']}\n"
                
                llm = AzureChatOpenAI(
                    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
                    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
                    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                    temperature=temp,
                    max_tokens=1000,
                ).with_structured_output(GitLabAnalysis)
                
                start_time = time.time()
                error = None
                prediction = None
                is_valid_format = False
                
                try:
                    response = await llm.ainvoke([
                        SystemMessage(content=SYSTEM_INSTRUCTIONS),
                        HumanMessage(content=formatted_input)
                    ])
                    prediction = response.model_dump()
                    is_valid_format = True
                except Exception as e:
                    error = str(e)
                
                latency = time.time() - start_time
                
                results.append({
                    "test_case_id": tc_id,
                    "category": category,
                    "temperature": temp,
                    "latency": latency,
                    "is_valid_format": is_valid_format,
                    "error": error,
                    "ground_truth": ground_truth,
                    "prediction": prediction
                })
            
            print(f"Temp {temp} Summary: {cb.total_tokens} tokens, ${cb.total_cost:.4f}")

        # Save result for this temperature
        output_file = os.path.join(output_dir, f"results_parameter({temp}).json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)
        print(f"Results saved to {output_file}")

if __name__ == "__main__":
    asyncio.run(run_experiment())
