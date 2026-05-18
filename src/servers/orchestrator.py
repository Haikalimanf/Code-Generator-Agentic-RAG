"""
Integration Orchestrator -- Predefined Workflow

Arsitektur: ZERO LLM di layer orchestrator.
Setiap task memanggil satu tool spesifik secara langsung (direct tool call).
LLM hanya ada di dalam masing-masing specialist MCP server.
"""

import os
import sys
import asyncio
import json
import logging
from typing import Dict, Any
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import FastMCP

from src.config.settings import settings

load_dotenv()

logger = logging.getLogger("orchestrator")

try:
    from src.servers.pdf_rag import run_compliance_expert_agent
    RAG_AVAILABLE = True
    RAG_ERROR_DETAIL = None
except Exception as e:
    RAG_AVAILABLE = False
    RAG_ERROR_DETAIL = str(e)

PYTHON_CMD = sys.executable
PROJECT_ROOT = settings.project_root

CONFIG_DIAGNOSTICS: Dict[str, Any] = {
    "POSTMAN_API_KEY": "Set" if settings.postman_api_key else "Not set",
    "POSTMAN_WORKSPACE_ID": "Set" if settings.postman_workspace_id else "Not set",
    "ANDROID_PROJECT_ROOT": "Set" if settings.android_project_root else "Not set",
    "RAG_AVAILABLE": RAG_AVAILABLE,
}
if not RAG_AVAILABLE:
    CONFIG_DIAGNOSTICS["RAG_ERROR"] = RAG_ERROR_DETAIL

logger.info("Environment config: %s", CONFIG_DIAGNOSTICS)

MCP_SERVERS_CONFIG: Dict[str, Any] = {}

if settings.android_project_root and Path(settings.android_project_root).exists():
    MCP_SERVERS_CONFIG["android_studio"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "servers" / "android_studio.py")],
        "transport": "stdio",
        "env": {**os.environ, "ANDROID_PROJECT_ROOT": settings.android_project_root},
    }
else:
    logger.warning("ANDROID_PROJECT_ROOT tidak valid: %s", settings.android_project_root)

if settings.postman_api_key:
    MCP_SERVERS_CONFIG["postman"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "servers" / "postman.py")],
        "transport": "stdio",
        "env": {
            **os.environ,
            "POSTMAN_API_KEY": settings.postman_api_key,
            "POSTMAN_WORKSPACE_ID": settings.postman_workspace_id,
        },
    }
else:
    logger.warning("POSTMAN_API_KEY tidak ada. Postman agent dinonaktifkan.")

MCP_SERVERS_CONFIG["figma"] = {
    "command": PYTHON_CMD,
    "args": [str(PROJECT_ROOT / "src" / "servers" / "figma.py"), "--server"],
    "transport": "stdio",
    "env": {**os.environ},
}

logger.info("MCP servers aktif: %s", list(MCP_SERVERS_CONFIG.keys()))


async def _call_tool(server_key: str, tool_name: str, tool_args: Dict) -> str | None:
    config = MCP_SERVERS_CONFIG.get(server_key)
    if not config:
        return None

    try:
        client = MultiServerMCPClient({server_key: config})
        tools = await client.get_tools()

        target = next((t for t in tools if tool_name in t.name), None)
        if not target:
            available = [t.name for t in tools]
            logger.error("Tool '%s' tidak ditemukan di '%s'. Tersedia: %s", tool_name, server_key, available)
            return None

        logger.info("Calling %s/%s ...", server_key, target.name)
        result = await target.ainvoke(tool_args)
        return str(result)

    except Exception as e:
        logger.error("Error calling %s/%s: %s", server_key, tool_name, e)
        return None


mcp = FastMCP(
    name="IntegrationOrchestrator",
    instructions=(
        "Predefined workflow orchestrator. "
        "Koordinasi Android Studio, Postman, Figma, dan RAG "
        "dengan direct tool calls -- tanpa LLM reasoning di layer ini."
    ),
)

FIGMA_NODE_MAP = {
    "login": "2335:6376",
    "register": "2335:6404",
    "chat": "2335:5716",
    "home": "2335:5799",
}


@mcp.tool()
async def get_complete_integration_context(
    requirement: str,
    include_api: bool = True,
    include_design: bool = False,
    include_kotlin_docs: bool = False,
    include_company_guidelines: bool = True,
) -> str:
    """
    [PREDEFINED WORKFLOW] Mengambil konteks teknis lengkap secara paralel.

    Args:
        requirement: Requirement dari GitLab issue
        include_api: Query Postman untuk API contracts
        include_design: Query Figma untuk design XML
        include_kotlin_docs: Dinonaktifkan (gunakan Context7 langsung)
        include_company_guidelines: Query RAG untuk pedoman coding perusahaan
    """
    logger.info("===== START PREDEFINED WORKFLOW =====")
    logger.info("Requirement (first 100 chars): %s", requirement[:100])

    results: Dict[str, Any] = {
        "requirement": requirement,
        "code_structure": None,
        "api_contracts": None,
        "design_context": None,
        "company_guidelines": None,
        "errors": [],
    }

    async def fetch_android_studio_context():
        if "android_studio" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Android Studio tidak dikonfigurasi (ANDROID_PROJECT_ROOT tidak valid)")
            return
        logger.info("[1/4] Android Studio context ...")
        output = await _call_tool(
            server_key="android_studio",
            tool_name="run_android_architect_agent",
            tool_args={"user_query": requirement},
        )
        if output:
            results["code_structure"] = output
            logger.info("[1/4] Android Studio DONE.")
        else:
            results["errors"].append("Android Studio: tidak ada data yang dikembalikan.")

    async def fetch_postman_api():
        if not include_api:
            logger.info("[2/4] Postman SKIPPED (include_api=False).")
            return
        if "postman" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Postman tidak dikonfigurasi (POSTMAN_API_KEY tidak ada)")
            return
        logger.info("[2/4] Postman API contracts ...")
        output = await _call_tool(
            server_key="postman",
            tool_name="run_postman_analyst_agent",
            tool_args={"user_query": requirement},
        )
        if output:
            results["api_contracts"] = output
            logger.info("[2/4] Postman DONE.")
        else:
            results["errors"].append("Postman: tidak ada data yang dikembalikan.")

    async def fetch_figma_context():
        if not include_design:
            logger.info("[3/4] Figma SKIPPED (include_design=False).")
            return
        if "figma" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Figma tidak dikonfigurasi")
            return

        req_lower = requirement.lower()
        node_id = next(
            (nid for kw, nid in FIGMA_NODE_MAP.items() if kw in req_lower),
            "2335:6376",
        )

        logger.info("[3/4] Figma XML untuk node %s ...", node_id)
        output = await _call_tool(
            server_key="figma",
            tool_name="get_figma_xml_metadata",
            tool_args={"node_id": node_id},
        )
        if output:
            results["design_context"] = output
            logger.info("[3/4] Figma DONE.")
        else:
            results["errors"].append(f"Figma: tidak ada data untuk node {node_id}.")

    async def fetch_company_guidelines():
        if not include_company_guidelines:
            logger.info("[4/4] RAG SKIPPED (include_company_guidelines=False).")
            return
        if not RAG_AVAILABLE:
            results["errors"].append(f"RAG tidak tersedia: {RAG_ERROR_DETAIL}")
            logger.error("[4/4] RAG UNAVAILABLE: %s", RAG_ERROR_DETAIL)
            return

        logger.info("[4/4] Company guidelines via RAG (thread) ...")
        try:
            result = await asyncio.to_thread(run_compliance_expert_agent, requirement)
            results["company_guidelines"] = result.model_dump_json(indent=2)
            logger.info("[4/4] RAG DONE.")
        except Exception as e:
            error_msg = f"RAG error: {e}"
            results["errors"].append(error_msg)
            logger.error("[4/4] %s", error_msg)

    await asyncio.gather(
        fetch_android_studio_context(),
        fetch_postman_api(),
        fetch_figma_context(),
        fetch_company_guidelines(),
        return_exceptions=True,
    )

    filled = sum(1 for k in ["code_structure", "api_contracts", "design_context", "company_guidelines"]
                 if results[k] is not None)
    logger.info("===== DONE (%d/4 sources filled, %d errors) =====", filled, len(results["errors"]))

    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
async def query_rag_directly(query: str) -> str:
    """
    Query RAG secara langsung untuk dokumen perusahaan.

    Args:
        query: Pertanyaan mengenai standar coding perusahaan
    """
    if not RAG_AVAILABLE:
        return f"RAG tidak tersedia: {RAG_ERROR_DETAIL}"

    try:
        logger.info("Direct RAG query: %s", query[:80])
        result = await asyncio.to_thread(run_compliance_expert_agent, query)
        return result.model_dump_json(indent=2)
    except Exception as e:
        return f"RAG Query error: {e}"


@mcp.tool()
async def health_check_all_servers() -> str:
    """
    Health check untuk semua MCP servers dan RAG.
    """
    results: Dict[str, Any] = {}

    for server_name, config in MCP_SERVERS_CONFIG.items():
        try:
            logger.info("Health Check: Testing %s...", server_name)
            client = MultiServerMCPClient({server_name: config})
            tools = await client.get_tools()
            results[server_name] = {
                "status": "ONLINE",
                "tools_count": len(tools),
                "available_tools": [t.name for t in tools],
            }
        except Exception as e:
            results[server_name] = {
                "status": "OFFLINE",
                "error": str(e),
                "command": config.get("command"),
                "args": config.get("args"),
            }

    results["rag"] = {
        "status": "AVAILABLE" if RAG_AVAILABLE else "UNAVAILABLE",
        "direct_access": True,
        "notes": "Direct import dari src.servers.pdf_rag (tanpa MCP)",
        "error": RAG_ERROR_DETAIL,
        "env_check": {
            "VECTOR_DATABASE_URL": "Set" if settings.vector_database_url else "Not set",
        },
    }

    return json.dumps(results, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    logger.info(
        "\nINTEGRATION ORCHESTRATOR -- Predefined Workflow\n"
        "Mode: ZERO LLM di layer orchestrator\n"
        "Direct tool calls ke specialist MCP servers\n\n"
        "Tools:\n"
        "  - get_complete_integration_context() -- main flow\n"
        "  - query_rag_directly()              -- RAG query\n"
        "  - health_check_all_servers()         -- status check\n"
    )
    mcp.run(transport="stdio")