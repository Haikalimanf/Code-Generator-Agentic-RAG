"""
Integration Orchestrator — Full Predefined Workflow

Arsitektur: ZERO LLM di layer orchestrator.
Setiap task memanggil satu tool spesifik secara langsung (direct tool call).
LLM hanya ada di dalam masing-masing specialist MCP server.

Flow:
  fetch_android_studio_context  → tool: run_android_architect_agent(user_query)
  fetch_postman_api             → tool: run_postman_analyst_agent(user_query)
  fetch_figma_context           → tool: get_figma_xml_metadata(node_id)
  fetch_company_guidelines      → langsung: run_compliance_expert_agent() via asyncio.to_thread
"""

import os
import sys
import asyncio
import json
import traceback
from typing import Dict, List, Optional, Any
from pathlib import Path
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import FastMCP

# ==================== RAG ENABLED ====================
try:
    from agent_pdf_rag import run_compliance_expert_agent
    RAG_AVAILABLE = True
    RAG_ERROR_DETAIL = None
except Exception as e:
    RAG_AVAILABLE = False
    RAG_ERROR_DETAIL = str(e)

load_dotenv()

# ==================== KONFIGURASI ====================
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o")

if not API_KEY:
    print("[WARNING] OPENROUTER_API_KEY belum diset.", file=sys.stderr)

PROJECT_ROOT = Path(__file__).parent.parent

POSTMAN_API_KEY       = os.getenv("POSTMAN_API_KEY", "").strip()
POSTMAN_WORKSPACE_ID  = os.getenv("POSTMAN_WORKSPACE_ID", "").strip()
ANDROID_PROJECT_ROOT  = os.getenv("ANDROID_PROJECT_ROOT", "").strip()

PYTHON_CMD = sys.executable

# ==================== DIAGNOSIS ====================
print("[Orchestrator] Environment variables loaded:", file=sys.stderr)
print(f"    POSTMAN_API_KEY      : {'Set' if POSTMAN_API_KEY else 'Not set'}", file=sys.stderr)
print(f"    POSTMAN_WORKSPACE_ID : {'Set' if POSTMAN_WORKSPACE_ID else 'Not set'}", file=sys.stderr)
print(f"    ANDROID_PROJECT_ROOT : {'Set' if ANDROID_PROJECT_ROOT else 'Not set'}", file=sys.stderr)
print(f"    RAG_AVAILABLE        : {RAG_AVAILABLE}", file=sys.stderr)
if not RAG_AVAILABLE:
    print(f"    RAG_ERROR            : {RAG_ERROR_DETAIL}", file=sys.stderr)

# ==================== MCP SERVER CONFIGS ====================
MCP_SERVERS_CONFIG: Dict[str, Any] = {}

if ANDROID_PROJECT_ROOT and Path(ANDROID_PROJECT_ROOT).exists():
    MCP_SERVERS_CONFIG["android_studio"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "agent_context_android_studio.py")],
        "transport": "stdio",
        "env": {**os.environ, "ANDROID_PROJECT_ROOT": ANDROID_PROJECT_ROOT},
    }
else:
    print(f"[Orchestrator] ANDROID_PROJECT_ROOT tidak valid: {ANDROID_PROJECT_ROOT}", file=sys.stderr)

if POSTMAN_API_KEY:
    MCP_SERVERS_CONFIG["postman"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "postman_context_server.py")],
        "transport": "stdio",
        "env": {
            **os.environ,
            "POSTMAN_API_KEY": POSTMAN_API_KEY,
            "POSTMAN_WORKSPACE_ID": POSTMAN_WORKSPACE_ID,
        },
    }
else:
    print("[Orchestrator] POSTMAN_API_KEY tidak ada. Postman agent dinonaktifkan.", file=sys.stderr)

MCP_SERVERS_CONFIG["figma"] = {
    "command": PYTHON_CMD,
    "args": [str(PROJECT_ROOT / "src" / "figma_context_server.py"), "--server"],
    "transport": "stdio",
    "env": {**os.environ},
}

print(f"[Orchestrator] MCP servers aktif: {list(MCP_SERVERS_CONFIG.keys())}", file=sys.stderr)

# ==================== HELPER ====================

async def _call_tool(server_key: str, tool_name: str, tool_args: Dict) -> Optional[str]:
    """
    Helper predefined: buka koneksi MCP, cari tool berdasarkan nama, panggil langsung.
    Tidak ada LLM. Tidak ada reasoning. Satu tool call, satu result.
    """
    config = MCP_SERVERS_CONFIG.get(server_key)
    if not config:
        return None

    try:
        client = MultiServerMCPClient({server_key: config})
        tools = await client.get_tools()

        # Cari tool berdasarkan nama (partial match)
        target = next((t for t in tools if tool_name in t.name), None)
        if not target:
            available = [t.name for t in tools]
            print(
                f"[Orchestrator] Tool '{tool_name}' tidak ditemukan di '{server_key}'. "
                f"Tersedia: {available}",
                file=sys.stderr,
            )
            return None

        print(f"[Orchestrator] Calling {server_key}/{target.name} ...", file=sys.stderr)
        result = await target.ainvoke(tool_args)
        return str(result)

    except Exception as e:
        print(f"[Orchestrator] Error calling {server_key}/{tool_name}: {e}", file=sys.stderr)
        return None


# ==================== MCP SERVER ORCHESTRATOR ====================
mcp = FastMCP(
    name="IntegrationOrchestrator",
    instructions=(
        "Predefined workflow orchestrator. "
        "Koordinasi Android Studio, Postman, Figma, dan RAG "
        "dengan direct tool calls — tanpa LLM reasoning di layer ini."
    ),
)


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

    Setiap sumber dipanggil dengan direct tool call — tidak ada LLM di layer ini.

    Args:
        requirement: Requirement dari GitLab issue
        include_api: Query Postman untuk API contracts
        include_design: Query Figma untuk design XML (butuh Figma Desktop aktif)
        include_kotlin_docs: Dinonaktifkan (gunakan Context7 secara langsung jika perlu)
        include_company_guidelines: Query RAG untuk pedoman coding perusahaan

    Returns:
        JSON string dengan aggregated context dari semua sumber
    """
    print(f"\n[Orchestrator] ===== START PREDEFINED WORKFLOW =====", file=sys.stderr)
    print(f"[Orchestrator] Requirement (first 100 chars): {requirement[:100]}", file=sys.stderr)

    results: Dict[str, Any] = {
        "requirement": requirement,
        "code_structure": None,
        "api_contracts": None,
        "design_context": None,
        "company_guidelines": None,
        "errors": [],
    }

    # ── TASK 1: Android Studio ───────────────────────────────────────────────
    async def fetch_android_studio_context():
        if "android_studio" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Android Studio tidak dikonfigurasi (ANDROID_PROJECT_ROOT tidak valid)")
            return
        print("[Orchestrator] [1/4] Android Studio context ...", file=sys.stderr)
        output = await _call_tool(
            server_key="android_studio",
            tool_name="run_android_architect_agent",
            tool_args={"user_query": requirement},
        )
        if output:
            results["code_structure"] = output
            print("[Orchestrator] [1/4] Android Studio DONE.", file=sys.stderr)
        else:
            results["errors"].append("Android Studio: tidak ada data yang dikembalikan.")

    # ── TASK 2: Postman API ──────────────────────────────────────────────────
    async def fetch_postman_api():
        if not include_api:
            print("[Orchestrator] [2/4] Postman SKIPPED (include_api=False).", file=sys.stderr)
            return
        if "postman" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Postman tidak dikonfigurasi (POSTMAN_API_KEY tidak ada)")
            return
        print("[Orchestrator] [2/4] Postman API contracts ...", file=sys.stderr)
        output = await _call_tool(
            server_key="postman",
            tool_name="run_postman_analyst_agent",
            tool_args={"user_query": requirement},
        )
        if output:
            results["api_contracts"] = output
            print("[Orchestrator] [2/4] Postman DONE.", file=sys.stderr)
        else:
            results["errors"].append("Postman: tidak ada data yang dikembalikan.")

    # ── TASK 3: Figma Design ─────────────────────────────────────────────────
    # Mapping kata kunci dari requirement → node ID Figma yang sudah diketahui
    FIGMA_NODE_MAP = {
        "login"    : "2335:6376",
        "register" : "2335:6404",
        "chat"     : "2335:5716",
        "home"     : "2335:5799",
    }

    async def fetch_figma_context():
        if not include_design:
            print("[Orchestrator] [3/4] Figma SKIPPED (include_design=False).", file=sys.stderr)
            return
        if "figma" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Figma tidak dikonfigurasi")
            return

        # Tentukan node ID berdasarkan kata kunci dalam requirement (predefined mapping)
        req_lower = requirement.lower()
        node_id = next(
            (nid for kw, nid in FIGMA_NODE_MAP.items() if kw in req_lower),
            "2335:6376",  # default ke halaman Login
        )

        print(f"[Orchestrator] [3/4] Figma XML untuk node {node_id} ...", file=sys.stderr)
        output = await _call_tool(
            server_key="figma",
            tool_name="get_figma_xml_metadata",
            tool_args={"node_id": node_id},
        )
        if output:
            results["design_context"] = output
            print("[Orchestrator] [3/4] Figma DONE.", file=sys.stderr)
        else:
            results["errors"].append(f"Figma: tidak ada data untuk node {node_id}. Pastikan Figma Desktop aktif.")

    # ── TASK 4: Company Guidelines via RAG ──────────────────────────────────
    async def fetch_company_guidelines():
        if not include_company_guidelines:
            print("[Orchestrator] [4/4] RAG SKIPPED (include_company_guidelines=False).", file=sys.stderr)
            return
        if not RAG_AVAILABLE:
            results["errors"].append(f"RAG tidak tersedia: {RAG_ERROR_DETAIL}")
            print(f"[Orchestrator] [4/4] RAG UNAVAILABLE: {RAG_ERROR_DETAIL}", file=sys.stderr)
            return

        print("[Orchestrator] [4/4] Company guidelines via RAG (thread) ...", file=sys.stderr)
        try:
            # run_compliance_expert_agent adalah sync — jalankan di thread agar tidak blokir event loop
            result = await asyncio.to_thread(run_compliance_expert_agent, requirement)
            results["company_guidelines"] = result.model_dump_json(indent=2)
            print("[Orchestrator] [4/4] RAG DONE.", file=sys.stderr)
        except Exception as e:
            error_msg = f"RAG error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"[Orchestrator] [4/4] {error_msg}", file=sys.stderr)

    # ── PARALLEL EXECUTION ───────────────────────────────────────────────────
    await asyncio.gather(
        fetch_android_studio_context(),
        fetch_postman_api(),
        fetch_figma_context(),
        fetch_company_guidelines(),
        return_exceptions=True,
    )

    # Hitung statistik
    filled = sum(1 for k in ["code_structure", "api_contracts", "design_context", "company_guidelines"]
                 if results[k] is not None)
    print(f"[Orchestrator] ===== DONE ({filled}/4 sources filled, {len(results['errors'])} errors) =====", file=sys.stderr)

    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
async def query_rag_directly(query: str) -> str:
    """
    Query RAG secara langsung untuk dokumen perusahaan.

    Args:
        query: Pertanyaan mengenai standar coding perusahaan

    Returns:
        JSON string hasil analisis ComplianceAnalysis
    """
    if not RAG_AVAILABLE:
        return f"RAG tidak tersedia: {RAG_ERROR_DETAIL}"

    try:
        print(f"[Orchestrator] Direct RAG query: {query[:80]}", file=sys.stderr)
        result = await asyncio.to_thread(run_compliance_expert_agent, query)
        return result.model_dump_json(indent=2)
    except Exception as e:
        return f"RAG Query error: {str(e)}"


@mcp.tool()
async def health_check_all_servers() -> str:
    """
    Health check untuk semua MCP servers dan RAG.

    Returns:
        JSON string status setiap server
    """
    results: Dict[str, Any] = {}

    for server_name, config in MCP_SERVERS_CONFIG.items():
        try:
            print(f"[Health Check] Testing {server_name}...", file=sys.stderr)
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
        "notes": "Direct import dari agent_pdf_rag.py (tanpa MCP)",
        "error": RAG_ERROR_DETAIL,
        "env_check": {
            "VECTOR_DATABASE_URL": "Set" if os.getenv("VECTOR_DATABASE_URL") else "Not set"
        },
    }

    return json.dumps(results, indent=2, ensure_ascii=False)


# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    print(
        "\n"
        "╔═════════════════════════════════════════════════════════╗\n"
        "║   INTEGRATION ORCHESTRATOR — Predefined Workflow        ║\n"
        "║                                                         ║\n"
        "║   Mode: ZERO LLM di layer orchestrator                  ║\n"
        "║   Direct tool calls ke specialist MCP servers           ║\n"
        "║                                                         ║\n"
        "║   Tools:                                                ║\n"
        "║   • get_complete_integration_context() — main flow      ║\n"
        "║   • query_rag_directly()              — RAG query       ║\n"
        "║   • health_check_all_servers()        — status check    ║\n"
        "╚═════════════════════════════════════════════════════════╝\n",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")
