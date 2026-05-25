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
from typing import Any

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
            "env": {
                **os.environ,
                "PYTHONPATH": str(settings.project_root),
            },
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
            raw_result = await asyncio.wait_for(
                integration_tool.ainvoke({
                    "requirement": requirement_spec,
                    "include_api": True,
                    "include_design": False,
                    "include_kotlin_docs": False,
                    "include_company_guidelines": True,
                }),
                timeout=600
            )
        except asyncio.TimeoutError:
            logger.error("Orchestrator timeout (>10 menit). Periksa koneksi ke sub-agents.")
            return


        # Extract clean text if raw_result is a list of LangChain message content blocks
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

        output_dir = settings.project_root / "outputs"
        output_dir.mkdir(exist_ok=True)

        filename = f"technical_context_issue_{issue_iid}.md"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Technical Context for Issue #{issue_iid}\n\n")
            f.write(final_context)

        logger.info("====== FINAL TECHNICAL CONTEXT ======")
        try:
            print(final_context)
        except UnicodeEncodeError:
            # Fallback untuk console Windows dengan encoding non-UTF-8
            encoding = sys.stdout.encoding or "utf-8"
            print(final_context.encode(encoding, errors="replace").decode(encoding))
        logger.info("SUCCESS: Result saved to %s", filepath)

    except Exception as e:
        logger.exception("Orchestration Stage Error:")



if __name__ == "__main__":
    TEST_PROJECT_ID = "81209841"
    TEST_ISSUE_IID = 1

    if len(sys.argv) > 2:
        asyncio.run(run_full_integration_flow(sys.argv[1], int(sys.argv[2])))
    else:
        logger.info("Menggunakan default issue: Project %s Issue #%d", TEST_PROJECT_ID, TEST_ISSUE_IID)
        asyncio.run(run_full_integration_flow(TEST_PROJECT_ID, TEST_ISSUE_IID))