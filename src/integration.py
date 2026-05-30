"""
CONTOH PRODUKSI: Integrasi GitLab Agent dengan Integration Orchestrator

Flow:
1. GitLab Agent: Menganalisis issue dan membuat technical requirement spec.
2. Integration Orchestrator: Mengambil spec tersebut dan menjalankan Planner-Executor
   dengan RAG specialist untuk mencari pedoman coding perusahaan.
3. Output: Dokumen context teknis lengkap untuk proses coding selanjutnya.

PERUBAHAN ARSITEKTUR:
- Sebelumnya: Orchestrator dijalankan sebagai MCP subprocess (via MultiServerMCPClient + stdio).
  Ini menyebabkan deadlock event loop karena FastMCP + LangGraph .stream() berkonflik.
- Sekarang: Orchestrator dipanggil LANGSUNG (in-process) sebagai async function.
  Ini menghilangkan semua masalah subprocess (stdout conflict, event loop deadlock, timeout).
"""

import asyncio
import json
import sys
import logging
from typing import Any

from src.config.settings import settings

# Konfigurasi logging agar output muncul di terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("integration")


async def run_full_integration_flow(project_id: str, issue_iid: int):
    print("\n" + "=" * 60)
    print("  🚀 FULL INTEGRATION FLOW START")
    print("=" * 60)
    logger.info("====== FULL INTEGRATION FLOW START ======")

    # ==================================================================
    # STEP 1: GitLab Agent → Requirement Spec
    # ==================================================================
    print("\n📌 [Step 1/3] Fetching & Analyzing GitLab Issue...")
    logger.info("[Step 1] Fetching & Analyzing GitLab Issue...")
    try:
        from src.agents.gitlab import run_gitlab_analyst_agent
        requirement_obj = run_gitlab_analyst_agent(project_id, issue_iid)

        requirement_spec = requirement_obj.model_dump_json(indent=2)
        print(f"   ✅ Requirement Spec Generated ({len(requirement_spec)} chars)")
        logger.info("DONE: Requirement Spec Generated (%d chars)", len(requirement_spec))
    except Exception as e:
        print(f"   ❌ GitLab Stage Error: {e}")
        logger.error("GitLab Stage Error: %s", e)
        return

    # ==================================================================
    # STEP 2: Orchestrator → Technical Context (DIRECT CALL, bukan subprocess)
    # ==================================================================
    print("\n📌 [Step 2/3] Querying Orchestrator for Technical Context...")
    print("   ⏳ Memanggil Orchestrator secara langsung (in-process)...")
    logger.info("[Step 2] Querying Orchestrator for Technical Context...")

    try:
        # Import orchestrator langsung — BUKAN sebagai MCP subprocess
        from src.servers.orchestrator import get_complete_integration_context

        print("   ⏳ Planner LLM + RAG agent sedang berjalan...")
        print("   💡 Proses ini membutuhkan panggilan ke OpenRouter LLM, harap bersabar.")

        # Panggil langsung sebagai async function (in-process)
        # Timeout 5 menit — seharusnya cukup karena tidak ada overhead subprocess
        raw_result = await asyncio.wait_for(
            get_complete_integration_context(
                requirement=requirement_spec,
                include_api=True,
                include_design=False,
                include_kotlin_docs=False,
                include_company_guidelines=True,
            ),
            timeout=300  # 5 menit (dulu 10 menit via subprocess)
        )

        print("   ✅ Orchestrator selesai!")

    except asyncio.TimeoutError:
        print("\n   ❌ TIMEOUT: Orchestrator membutuhkan waktu > 5 menit.")
        print("   💡 Kemungkinan penyebab:")
        print("      - OpenRouter LLM tidak merespon (cek API key & koneksi internet)")
        print("      - RAG agent hang (cek koneksi ke PostgreSQL / PGVector)")
        logger.error("Orchestrator timeout (>5 menit).")
        return
    except Exception as e:
        print(f"\n   ❌ Orchestration Error: {e}")
        logger.exception("Orchestration Stage Error:")
        return

    # ==================================================================
    # STEP 3: Format & Save Output
    # ==================================================================
    # raw_result sudah berupa Markdown string dari consolidation_node
    raw_result_str = raw_result
    if isinstance(raw_result, list):
        texts = []
        for item in raw_result:
            if hasattr(item, "text"):
                texts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
            else:
                texts.append(str(item))
        raw_result_str = "\n".join(texts)

    def _format_json_field(val: Any) -> str:
        if not val:
            return ""
        if isinstance(val, str):
            try:
                parsed_val = json.loads(val)
                return json.dumps(parsed_val, indent=2, ensure_ascii=False)
            except Exception:
                return val
        try:
            return json.dumps(val, indent=2, ensure_ascii=False)
        except Exception:
            return str(val)

    try:
        # Check if raw_result_str is a JSON string (for backward compatibility / fallback)
        if isinstance(raw_result_str, str) and raw_result_str.strip().startswith(("{", "[")):
            parsed = json.loads(raw_result_str)
            sections = []
            if parsed.get("code_structure"):
                sections.append(f"## 1. Struktur & File Project (Android Studio)\n\n```json\n{_format_json_field(parsed['code_structure'])}\n```")
            if parsed.get("api_contracts"):
                sections.append(f"## 2. API Contracts (Postman)\n\n```json\n{_format_json_field(parsed['api_contracts'])}\n```")
            if parsed.get("design_context"):
                sections.append(f"## 3. Desain UI & XML (Figma)\n\n```json\n{_format_json_field(parsed['design_context'])}\n```")
            if parsed.get("company_guidelines"):
                sections.append(f"## 4. Pedoman Coding & Best Practices (RAG)\n\n```json\n{_format_json_field(parsed['company_guidelines'])}\n```")
            if parsed.get("errors"):
                sections.append(f"## Errors & Peringatan\n\n" + "\n".join(f"- {e}" for e in parsed["errors"]))
            final_context = "\n\n---\n\n".join(sections) if sections else raw_result_str
        else:
            # Already in Markdown format from Orchestrator
            final_context = raw_result_str
    except Exception as e:
        logger.warning("Gagal men-parse output: %s. Menggunakan raw string.", e)
        final_context = raw_result_str

    # Write to legacy/global output folder
    output_dir = settings.project_root / "outputs"
    output_dir.mkdir(exist_ok=True)
    filename = f"technical_context_issue_{issue_iid}.md"
    filepath = output_dir / filename

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Technical Context for Issue #{issue_iid}\n\n")
        f.write(final_context)

    # Write to stage-specific ICM output folder as the "edit surface"
    icm_output_dir = settings.project_root / "workspace" / "stages" / "inceptions" / "output"
    icm_output_dir.mkdir(parents=True, exist_ok=True)
    icm_filepath = icm_output_dir / "technical_blueprint.md"

    with open(icm_filepath, "w", encoding="utf-8") as f:
        f.write(final_context)

    print(f"\n📌 [Step 3/3] Output Generated!")
    print(f"   ✅ Legacy File: {filepath}")
    print(f"   ✅ ICM Stage Output (Edit Surface): {icm_filepath}")
    print(f"   📄 Ukuran output: {len(final_context)} karakter")
    logger.info("====== FINAL TECHNICAL CONTEXT ======")
    try:
        print("\n" + "=" * 60)
        print(final_context[:500] + ("\n..." if len(final_context) > 500 else ""))
        print("=" * 60)
    except UnicodeEncodeError:
        # Fallback untuk console Windows dengan encoding non-UTF-8
        encoding = sys.stdout.encoding or "utf-8"
        print(final_context[:500].encode(encoding, errors="replace").decode(encoding))
    logger.info("SUCCESS: Result saved to %s and %s", filepath, icm_filepath)



if __name__ == "__main__":
    TEST_PROJECT_ID = "81209841"
    TEST_ISSUE_IID = 1

    if len(sys.argv) > 2:
        asyncio.run(run_full_integration_flow(sys.argv[1], int(sys.argv[2])))
    else:
        print(f"Menggunakan default issue: Project {TEST_PROJECT_ID} Issue #{TEST_ISSUE_IID}")
        logger.info("Menggunakan default issue: Project %s Issue #%d", TEST_PROJECT_ID, TEST_ISSUE_IID)
        asyncio.run(run_full_integration_flow(TEST_PROJECT_ID, TEST_ISSUE_IID))