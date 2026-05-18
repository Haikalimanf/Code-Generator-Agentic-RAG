"""
CONTOH PRODUKSI: Integrasi GitLab Agent dengan Integration Orchestrator

Flow:
1. GitLab Agent: Menganalisis issue dan membuat technical requirement spec.
2. Integration Orchestrator: Mengambil spec tersebut dan mencari context di Android Studio, Postman, Figma, dan RAG.
3. Output: Dokumen context teknis lengkap untuk proses coding selanjutnya.
"""

import asyncio
import json
import os
import sys
import logging
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config.settings import settings

logger = logging.getLogger("integration")

ORCHESTRATOR_PATH = str(settings.project_root / "src" / "servers" / "orchestrator.py")


async def run_full_integration_flow(project_id: str, issue_iid: int):
    logger.info("====== FULL INTEGRATION FLOW START ======")

    logger.info("[Step 1] Fetching & Analyzing GitLab Issue...")
    try:
        from src.agents.gitlab import run_gitlab_analyst_agent
        requirement_obj = run_gitlab_analyst_agent(project_id, issue_iid)

        requirement_spec = requirement_obj.model_dump_json(indent=2)
        logger.info("DONE: Requirement Spec Generated (%d chars)", len(requirement_spec))
    except Exception as e:
        logger.error("GitLab Stage Error: %s", e)
        return

    logger.info("[Step 2] Querying Orchestrator for Technical Context...")

    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }

    try:
        logger.info("Menginisialisasi koneksi ke Orchestrator...")
        client = MultiServerMCPClient(orchestrator_config)
        tools = await client.get_tools()

        if not tools:
            logger.error("Orchestrator tidak mengembalikan tools. Periksa orchestrator.py.")
            return

        logger.info("Tools tersedia: %s", [t.name for t in tools])

        integration_tool = next(
            (t for t in tools if t.name == "get_complete_integration_context"), None
        )

        if not integration_tool:
            logger.error("Tool 'get_complete_integration_context' tidak ditemukan di Orchestrator.")
            return

        logger.info("Memanggil Orchestrator tool secara langsung (no agent loop)...")
        logger.info("Android Studio + Postman + RAG berjalan paralel, harap tunggu...")

        try:
            async with asyncio.timeout(600):
                raw_result = await integration_tool.ainvoke({
                    "requirement": requirement_spec,
                    "include_api": True,
                    "include_design": False,
                    "include_kotlin_docs": False,
                    "include_company_guidelines": True,
                })
        except asyncio.TimeoutError:
            logger.error("Orchestrator timeout (>10 menit). Periksa koneksi ke sub-agents.")
            return

        try:
            parsed = json.loads(raw_result) if isinstance(raw_result, str) else raw_result
            sections = []
            if parsed.get("code_structure"):
                sections.append(f"## 1. Struktur & File Project (Android Studio)\n\n{parsed['code_structure']}")
            if parsed.get("api_contracts"):
                sections.append(f"## 2. API Contracts (Postman)\n\n{parsed['api_contracts']}")
            if parsed.get("design_context"):
                sections.append(f"## 3. Desain UI & XML (Figma)\n\n{parsed['design_context']}")
            if parsed.get("company_guidelines"):
                sections.append(f"## 4. Pedoman Coding & Best Practices (RAG)\n\n{parsed['company_guidelines']}")
            if parsed.get("errors"):
                sections.append(f"## Errors & Peringatan\n\n" + "\n".join(f"- {e}" for e in parsed["errors"]))
            final_context = "\n\n---\n\n".join(sections) if sections else str(raw_result)
        except (json.JSONDecodeError, AttributeError):
            final_context = str(raw_result)

        output_dir = settings.project_root / "outputs"
        output_dir.mkdir(exist_ok=True)

        filename = f"technical_context_issue_{issue_iid}.md"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Technical Context for Issue #{issue_iid}\n\n")
            f.write(final_context)

        logger.info("====== FINAL TECHNICAL CONTEXT ======")
        print(final_context)
        logger.info("SUCCESS: Result saved to %s", filepath)

    except Exception as e:
        logger.error("Orchestration Stage Error: %s", e)


if __name__ == "__main__":
    TEST_PROJECT_ID = "81209841"
    TEST_ISSUE_IID = 1

    if len(sys.argv) > 2:
        asyncio.run(run_full_integration_flow(sys.argv[1], int(sys.argv[2])))
    else:
        logger.info("Menggunakan default issue: Project %s Issue #%d", TEST_PROJECT_ID, TEST_ISSUE_IID)
        asyncio.run(run_full_integration_flow(TEST_PROJECT_ID, TEST_ISSUE_IID))