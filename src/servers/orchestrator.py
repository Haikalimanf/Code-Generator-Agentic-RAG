"""
Integration Orchestrator -- Planner-Executor Architecture (LangGraph)

Arsitektur: LLM Planner di layer orchestrator dengan Context Engineering.
Planner menganalisis requirement, melakukan dekomposisi tugas, dan membuat
PLAN UNIK untuk setiap agen spesialis — bukan meneruskan user story mentah.

Prinsip Context Engineering:
- Setiap agen (Executor) hanya menerima instruksi dan konteks yang relevan
  untuk domainnya, memaksimalkan akurasi dan efisiensi token.

Migrasi dari: Zero-LLM hardcoded asyncio.gather()
Migrasi ke:   LangGraph StateGraph + Planner Node + Dynamic Routing + Context Engineering

AGEN YANG AKTIF: Hanya RAG (fokus development & testing)
Untuk mengaktifkan agen lain, cari komentar "# <-- UNCOMMENT" di seluruh file.
"""

import os
import sys
import asyncio
import json
import logging
import operator
from typing import Dict, Any, List, Optional, Annotated, TypedDict
from pathlib import Path

from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient
from fastmcp import FastMCP
from langgraph.graph import StateGraph, START, END

from src.config.settings import settings
from src.utils.llm_factory import create_llm, load_stage_prompt
from src.models.schemas import PlannerDecision

load_dotenv()

# Konfigurasi logging ke STDERR (PENTING: stdout dipakai MCP JSON-RPC stdio transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("orchestrator")
# ---------------------------------------------------------------------------
# RAG Import (direct, bukan MCP subprocess)
# ---------------------------------------------------------------------------
try:
    from src.servers.pdf_rag import run_compliance_expert_agent
    RAG_AVAILABLE = True
    RAG_ERROR_DETAIL = None
except Exception as e:
    RAG_AVAILABLE = False
    RAG_ERROR_DETAIL = str(e)

# ---------------------------------------------------------------------------
# Constants & Config Diagnostics
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# MCP Servers Config (conditional registration)
#
# SAAT INI HANYA RAG YANG AKTIF.
# Untuk mengaktifkan agen lain, uncomment blok konfigurasi di bawah.
# ---------------------------------------------------------------------------
MCP_SERVERS_CONFIG: Dict[str, Any] = {}

# <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
# if settings.android_project_root and Path(settings.android_project_root).exists():
#     MCP_SERVERS_CONFIG["android_studio"] = {
#         "command": PYTHON_CMD,
#         "args": [str(PROJECT_ROOT / "src" / "servers" / "android_studio.py")],
#         "transport": "stdio",
#         "env": {**os.environ, "ANDROID_PROJECT_ROOT": settings.android_project_root},
#     }
# else:
#     logger.warning("ANDROID_PROJECT_ROOT tidak valid: %s", settings.android_project_root)

# <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
# if settings.postman_api_key:
#     MCP_SERVERS_CONFIG["postman"] = {
#         "command": PYTHON_CMD,
#         "args": [str(PROJECT_ROOT / "src" / "servers" / "postman.py")],
#         "transport": "stdio",
#         "env": {
#             **os.environ,
#             "POSTMAN_API_KEY": settings.postman_api_key,
#             "POSTMAN_WORKSPACE_ID": settings.postman_workspace_id,
#         },
#     }
# else:
#     logger.warning("POSTMAN_API_KEY tidak ada. Postman agent dinonaktifkan.")

# <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
# MCP_SERVERS_CONFIG["figma"] = {
#     "command": PYTHON_CMD,
#     "args": [str(PROJECT_ROOT / "src" / "servers" / "figma.py"), "--server"],
#     "transport": "stdio",
#     "env": {**os.environ},
# }

# RAG is called directly in-process via asyncio.to_thread rather than as an MCP subprocess.

logger.info("MCP servers aktif: %s", list(MCP_SERVERS_CONFIG.keys()))

# ---------------------------------------------------------------------------
# Figma Node Map (keyword → Figma node ID)
# <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
# FIGMA_NODE_MAP = {
#     "login": "2335:6376",
#     "register": "2335:6404",
#     "chat": "2335:5716",
#     "home": "2335:5799",
# }


# ---------------------------------------------------------------------------
# _call_tool helper (preserved from original)
# ---------------------------------------------------------------------------
def _clean_tool_output(result: Any) -> str:
    if result is None:
        return ""
    
    if isinstance(result, list):
        texts = []
        for item in result:
            if hasattr(item, "text"):
                texts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            elif isinstance(item, str):
                texts.append(item)
            else:
                texts.append(str(item))
        return "\n".join(texts)
    
    if hasattr(result, "text"):
        return result.text
    if isinstance(result, dict) and "text" in result:
        return result["text"]
        
    return str(result)


def _extract_story(requirement: str) -> str:
    if not requirement:
        return ""
    try:
        data = json.loads(requirement)
        if isinstance(data, dict) and "story" in data:
            return data["story"]
    except Exception:
        pass
    return requirement


async def _call_tool(server_key: str, tool_name: str, tool_args: Dict) -> str | None:
    """Memanggil satu tool dari satu MCP server secara dinamis."""
    config = MCP_SERVERS_CONFIG.get(server_key)
    if not config:
        return None

    async def _execute():
        client = MultiServerMCPClient({server_key: config})
        tools = await client.get_tools()

        target = next((t for t in tools if tool_name in t.name), None)
        if not target:
            available = [t.name for t in tools]
            logger.error("Tool '%s' tidak ditemukan di '%s'. Tersedia: %s", tool_name, server_key, available)
            return None

        logger.info("Calling %s/%s ...", server_key, target.name)
        result = await target.ainvoke(tool_args)
        return _clean_tool_output(result)

    try:
        # Maksimal 120 detik per panggilan tool sub-agent agar tidak hang selamanya
        return await asyncio.wait_for(_execute(), timeout=120.0)
    except asyncio.TimeoutError:
        logger.error("Timeout memanggil %s/%s (>120 detik)", server_key, tool_name)
        return None
    except Exception as e:
        logger.error("Error calling %s/%s: %s", server_key, tool_name, e)
        return None



# ============================================================
# LangGraph: State Definition
# ============================================================
class OrchestratorState(TypedDict):
    """State global untuk orchestrator graph.

    Arsitektur Planner-Executor:
    - Planner (Supervisor): Melakukan dekomposisi tugas dan Context Engineering,
      memastikan setiap agen hanya menerima instruksi yang relevan.
    - Executor (Specialist Nodes): Menjalankan instruksi spesifik dari Planner.

    Fields:
        requirement:         Input user story / GitLab requirement.
        agent_plan:          Mapping dari nama agen ke plan terstruktur (SpecialistTask).
                             Setiap agen menerima INSTRUKSI UNIK, bukan user story mentah.
        code_structure:      Output dari Android Studio specialist.  (OFF)
        api_contracts:       Output dari Postman specialist.         (OFF)
        design_context:      Output dari Figma specialist.           (OFF)
        company_guidelines:  Output dari RAG specialist.            (ACTIVE)
        errors:              Akumulasi error dari seluruh specialist (reducer: add).
        consolidated_output: Output Markdown akhir dari Consolidation Node.
    """
    requirement: str
    agent_plan: Dict[str, dict]
    code_structure: Optional[str]
    api_contracts: Optional[str]
    design_context: Optional[str]
    company_guidelines: Optional[str]
    errors: Annotated[List[str], operator.add]
    consolidated_output: Optional[str]


# ============================================================
# ============================================================
# LangGraph: Planner Node
# ============================================================

# Agen yang saat ini aktif. Tambahkan "android_studio", "postman", "figma"
# saat ingin mengaktifkannya (pastikan juga uncomment di graph, schema, dsb).
ACTIVE_AGENTS = ["rag"]


async def supervisor_node(state: OrchestratorState) -> dict:
    """Planner Node: menganalisis requirement, melakukan dekomposisi tugas dengan Context Engineering.

    Setiap agen spesialis menerima PLAN yang UNIK dan TERFOKUS, bukan user story mentah.
    Ini memastikan efisiensi token dan akurasi output per agen.
    """
    requirement = state["requirement"]
    story = _extract_story(requirement)
    logger.info("🧠 [Planner] Menganalisis requirement dan membuat plan unik per agen...")

    available_agents = list(ACTIVE_AGENTS)
    if RAG_AVAILABLE and "rag" not in available_agents:
        available_agents.append("rag")
    elif not RAG_AVAILABLE and "rag" in available_agents:
        available_agents.remove("rag")

    try:
        llm = create_llm(temperature=0.0)
        llm_structured = llm.with_structured_output(PlannerDecision, method="function_calling")

        supervisor_prompt_tmpl = load_stage_prompt("inceptions")
        prompt = supervisor_prompt_tmpl.replace(
            "{active_servers}", ", ".join(available_agents)
        ).replace(
            "{rag_status}", "AVAILABLE" if RAG_AVAILABLE else f"UNAVAILABLE ({RAG_ERROR_DETAIL})"
        ).replace(
            "{requirement}", story
        )

        result: PlannerDecision = await llm_structured.ainvoke(prompt)

        # Filter: hanya agen yang benar-benar aktif/tersedia dan punya task non-kosong
        filtered_plan = {}
        for agent_name in available_agents:
            task_data = getattr(result, agent_name, None)
            if task_data and task_data.task:
                filtered_plan[agent_name] = task_data.model_dump()

        if not filtered_plan and available_agents:
            logger.warning("[Planner] LLM tidak menghasilkan plan valid. Membuat plan fallback.")
            for agent in available_agents:
                if agent == "rag":
                    filtered_plan["rag"] = {
                        "task": f"Cari pedoman coding perusahaan yang relevan dengan fitur berikut: {story[:300]}",
                        "focus_areas": ["naming conventions", "architecture patterns", "best practices"],
                        "context_scope": story[:500],
                        "expected_output": "Analisis standar coding dan best practices yang relevan",
                    }
                    # <-- UNCOMMENT saat ingin mengaktifkan agen lain:
                    # elif agent == "android_studio":
                    #     filtered_plan["android_studio"] = { ... }
                    # elif agent == "postman":
                    #     filtered_plan["postman"] = { ... }
                    # elif agent == "figma":
                    #     filtered_plan["figma"] = { ... }

        logger.info("[Planner] Routing decision: %s", list(filtered_plan.keys()))
        logger.info("[Planner] Reasoning: %s", result.reasoning)
        for agent, plan in filtered_plan.items():
            logger.info("[Planner] Plan for '%s': task='%s'", agent, plan.get("task", "")[:80])

        return {"agent_plan": filtered_plan}

    except Exception as e:
        logger.error("[Planner] LLM Error: %s. Fallback: membuat plan generik.", e, exc_info=True)
        fallback_plan = {}
        for agent in available_agents:
            fallback_plan[agent] = {
                "task": f"Cari konteks teknis terkait: {story[:200]}",
                "focus_areas": ["implementasi fitur"],
                "context_scope": story[:300],
                "expected_output": "Analisis konteks teknis untuk fitur yang diminta",
            }
        return {
            "agent_plan": fallback_plan,
            "errors": [f"Planner LLM error (fallback to generic plans): {e}"],
        }


# ============================================================
# LangGraph: Dynamic Routing Function
# ============================================================

AGENT_TO_NODE = {
    "android_studio": "android_studio_node",
    "postman": "postman_node",
    "figma": "figma_node",
    "rag": "rag_node",
}


def route_to_specialists(state: OrchestratorState) -> list[str]:
    """Dynamic routing berdasarkan keputusan Planner.

    Mengembalikan list nama node (str) untuk fan-out paralel.
    Jika tidak ada agen yang memiliki plan, langsung ke consolidation.
    """
    plan = state.get("agent_plan", {})

    if not plan:
        logger.warning("Tidak ada agen yang memiliki plan. Langsung ke konsolidasi.")
        return ["consolidation_node"]

    targets = []
    for agent in plan.keys():
        node_name = AGENT_TO_NODE.get(agent)
        if node_name:
            targets.append(node_name)
        else:
            logger.warning("Unknown agent '%s', skipping.", agent)

    return targets if targets else ["consolidation_node"]



# ============================================================
# LangGraph: Specialist Nodes
# ============================================================

# <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
# async def android_studio_node(state: OrchestratorState) -> dict:
#     """Specialist Node: Android Studio — project structure & architecture."""
#     plan = state.get("agent_plan", {}).get("android_studio", {})
#     task = plan.get("task", "")
#     focus_areas = plan.get("focus_areas", [])
#     context_scope = plan.get("context_scope", "")
#     expected_output = plan.get("expected_output", "")
#     logger.info("[Android Studio] Menjalankan plan terstruktur...")
#     result = await _call_tool("android_studio", "run_android_architect_agent", {"user_query": task})
#     if result is None:
#         return {"code_structure": "Android Studio agent tidak tersedia atau timeout.", "errors": ["android_studio: no response"]}
#     return {"code_structure": result}


# <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
# async def postman_node(state: OrchestratorState) -> dict:
#     """Specialist Node: Postman — API contracts & endpoints."""
#     plan = state.get("agent_plan", {}).get("postman", {})
#     task = plan.get("task", "")
#     focus_areas = plan.get("focus_areas", [])
#     context_scope = plan.get("context_scope", "")
#     expected_output = plan.get("expected_output", "")
#     logger.info("[Postman] Menjalankan plan terstruktur...")
#     result = await _call_tool("postman", "run_postman_analyst_agent", {"user_query": task})
#     if result is None:
#         return {"api_contracts": "Postman agent tidak tersedia atau timeout.", "errors": ["postman: no response"]}
#     return {"api_contracts": result}


# <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
# async def figma_node(state: OrchestratorState) -> dict:
#     """Specialist Node: Figma — UI design XML metadata."""
#     plan = state.get("agent_plan", {}).get("figma", {})
#     task = plan.get("task", "")
#     focus_areas = plan.get("focus_areas", [])
#     context_scope = plan.get("context_scope", "")
#     expected_output = plan.get("expected_output", "")
#     logger.info("[Figma] Menjalankan plan terstruktur...")
#     search_text = f"{task} {context_scope}".lower()
#     node_id = next(
#         (nid for kw, nid in FIGMA_NODE_MAP.items() if kw in search_text),
#         "2335:6376",
#     )
#     result = await _call_tool("figma", "get_figma_xml_metadata", {"node_id": node_id})
#     if result is None:
#         return {"design_context": "Figma agent tidak tersedia atau timeout.", "errors": ["figma: no response"]}
#     return {"design_context": result}


async def rag_node(state: OrchestratorState) -> dict:
    """Specialist Node: RAG — company guidelines & coding standards.

    Dipanggil secara langsung (direct import) tanpa MCP subprocess.
    Menerima plan terstruktur dari Planner (Context Engineering), bukan user story mentah.

    run_compliance_expert_agent() menggunakan LangGraph .stream() (synchronous).
    Dijalankan via asyncio.to_thread() agar tidak memblokir event loop utama.
    Ini aman karena integration.py sekarang memanggil orchestrator secara in-process
    (bukan sebagai MCP subprocess), sehingga tidak ada konflik event loop.
    """
    plan = state.get("agent_plan", {}).get("rag", {})
    task = plan.get("task", "")

    if not task:
        logger.warning("[RAG] Tidak ada task dari Planner. Menggunakan requirement sebagai fallback.")
        task = _extract_story(state.get("requirement", ""))

    if not RAG_AVAILABLE:
        logger.error("RAG agent tidak tersedia: %s", RAG_ERROR_DETAIL)
        return {"company_guidelines": f"RAG tidak tersedia: {RAG_ERROR_DETAIL}"}

    try:
        logger.info("[RAG] Memanggil compliance expert agent...")
        logger.info("[RAG] Task: %s", task[:100])
        result = await asyncio.to_thread(run_compliance_expert_agent, task)
        logger.info("[RAG] Compliance expert agent DONE.")
        return {"company_guidelines": result.model_dump_json(indent=2)}
    except Exception as e:
        logger.exception("[RAG] Error memanggil agent RAG:")
        return {
            "company_guidelines": f"Error memanggil agent RAG: {e}",
            "errors": [f"RAG agent error: {e}"]
        }



# ============================================================
# LangGraph: Consolidation Node
# ============================================================

async def consolidation_node(state: OrchestratorState) -> dict:
    """Consolidation Node: menyusun output akhir dari semua specialist dalam bentuk Markdown.

    Menampilkan juga rincian plan hasil dekomposisi Planner (Context Engineering)
    agar transparan bagaimana setiap agen menerima instruksi terfokus.
    """
    logger.info("📋 [Consolidation] Menyusun output akhir ke format Markdown...")

    # Helper untuk merapikan JSON strings jika ada
    def format_json_field(val: Any) -> str:
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

    sections = []
    sections.append("# Technical Integration Context Blueprint\n")
    
    # Bagian Requirement
    req = state["requirement"]
    try:
        req_parsed = json.loads(req)
        if isinstance(req_parsed, dict):
            req_md = ""
            if "role" in req_parsed:
                req_md += f"- **Role**: {req_parsed['role']}\n"
            if "goal" in req_parsed:
                req_md += f"- **Goal**: {req_parsed['goal']}\n"
            if "benefit" in req_parsed:
                req_md += f"- **Benefit**: {req_parsed['benefit']}\n"
            if "story" in req_parsed:
                req_md += f"- **User Story**: {req_parsed['story']}\n"
            if req_md:
                sections.append(f"## Kebutuhan Sistem / Requirement\n\n{req_md}")
            else:
                sections.append(f"## Kebutuhan Sistem / Requirement\n\n```json\n{json.dumps(req_parsed, indent=2, ensure_ascii=False)}\n```")
        else:
            sections.append(f"## Kebutuhan Sistem / Requirement\n\n{req}")
    except Exception:
        sections.append(f"## Kebutuhan Sistem / Requirement\n\n{req}")

    # Bagian Planner Decision & Detail Tugas (Context Engineering)
    agent_plan = state.get("agent_plan", {})
    if agent_plan:
        agent_list = ", ".join([f"`{a}`" for a in agent_plan.keys()])
        sections.append(f"**Specialist Agents Terlibat**: {agent_list}\n")

        sections.append("### Rincian Plan Hasil Dekomposisi (Planner → Context Engineering)")
        sections.append("")
        for agent, plan_data in agent_plan.items():
            task = plan_data.get("task", "—")
            focus = plan_data.get("focus_areas", [])
            scope = plan_data.get("context_scope", "—")
            expected = plan_data.get("expected_output", "—")
            sections.append(f"#### `{agent}`")
            sections.append(f"- **Task**: {task}")
            sections.append(f"- **Focus Areas**: {', '.join(focus) if isinstance(focus, list) else focus}")
            sections.append(f"- **Context Scope**: {scope}")
            sections.append(f"- **Expected Output**: {expected}")
            sections.append("")

    # <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
    # if state.get("code_structure"):
    #     code_struct = format_json_field(state["code_structure"])
    #     sections.append(f"## 1. Struktur & File Project (Android Studio)\n\n```json\n{code_struct}\n```")

    # <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
    # if state.get("api_contracts"):
    #     api_contracts = format_json_field(state["api_contracts"])
    #     sections.append(f"## 2. API Contracts (Postman)\n\n```json\n{api_contracts}\n```")

    # <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
    # if state.get("design_context"):
    #     design_context = format_json_field(state["design_context"])
    #     sections.append(f"## 3. Desain UI & XML (Figma)\n\n```json\n{design_context}\n```")

    # Bagian: Pedoman Coding & Best Practices (RAG) — AKTIF
    if state.get("company_guidelines"):
        company_guidelines = format_json_field(state["company_guidelines"])
        sections.append(f"## Pedoman Coding & Best Practices (RAG)\n\n```json\n{company_guidelines}\n```")

    # Bagian Errors & Peringatan
    errors = state.get("errors", [])
    if errors:
        error_list = "\n".join(f"- {e}" for e in errors)
        sections.append(f"## Errors & Peringatan Selama Proses\n\n{error_list}")

    markdown_output = "\n\n---\n\n".join(sections)
    
    filled = sum(
        1 for k in ["company_guidelines"]
        if state.get(k) is not None
    )
    logger.info(
        "📋 [Consolidation] DONE (RAG sources: %d, errors: %d)",
        filled, len(errors),
    )

    return {"consolidated_output": markdown_output}


# ============================================================
# LangGraph: Build & Compile Graph
# ============================================================

def _build_orchestrator_graph():
    """Membangun dan mengkompilasi orchestrator StateGraph.

    Flow (saat ini hanya RAG aktif):
        START → planner_node → [rag_node] → consolidation_node → END

    Untuk mengaktifkan agen lain, uncomment node dan edge yang sesuai.
    """
    graph = StateGraph(OrchestratorState)

    # -- Nodes --
    graph.add_node("supervisor_node", supervisor_node)
    # <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
    # graph.add_node("android_studio_node", android_studio_node)
    # <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
    # graph.add_node("postman_node", postman_node)
    # <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
    # graph.add_node("figma_node", figma_node)
    graph.add_node("rag_node", rag_node)
    graph.add_node("consolidation_node", consolidation_node)

    # -- Edges --
    graph.add_edge(START, "supervisor_node")

    # Fan-out: Planner → dynamic routing ke specialist nodes (paralel)
    graph.add_conditional_edges(
        "supervisor_node",
        route_to_specialists,
        path_map={
            # <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
            # "android_studio_node": "android_studio_node",
            # <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
            # "postman_node": "postman_node",
            # <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
            # "figma_node": "figma_node",
            "rag_node": "rag_node",
            "consolidation_node": "consolidation_node",
        }
    )

    # Fan-in: Semua specialist → consolidation (LangGraph menunggu semua selesai)
    # <-- UNCOMMENT saat ingin mengaktifkan agen Android Studio:
    # graph.add_edge("android_studio_node", "consolidation_node")
    # <-- UNCOMMENT saat ingin mengaktifkan agen Postman:
    # graph.add_edge("postman_node", "consolidation_node")
    # <-- UNCOMMENT saat ingin mengaktifkan agen Figma:
    # graph.add_edge("figma_node", "consolidation_node")
    graph.add_edge("rag_node", "consolidation_node")

    graph.add_edge("consolidation_node", END)

    return graph.compile()


orchestrator_graph = _build_orchestrator_graph()
logger.info("LangGraph orchestrator compiled successfully.")


# ============================================================
# FastMCP Server (Backward Compatible Interface)
# ============================================================

mcp = FastMCP(
    name="IntegrationOrchestrator",
    instructions=(
        "AI-Driven Autonomous Orchestrator (Planner-Executor Architecture). "
        "Planner LLM menganalisis requirement, melakukan dekomposisi tugas dengan Context Engineering, "
        "dan membuat plan unik per specialist. Setiap specialist (Executor) hanya menerima "
        "konteks yang relevan untuk domainnya, bukan user story mentah. "
        "Saat ini aktif: RAG only. Lihat komentar '# <-- UNCOMMENT' untuk mengaktifkan agen lain."
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
    [PLANNER-EXECUTOR WORKFLOW] Mengambil konteks teknis lengkap secara otonom.

    Planner LLM menganalisis requirement, melakukan dekomposisi tugas (Context Engineering),
    dan membuat PLAN UNIK untuk setiap specialist. Setiap specialist (Executor) hanya
    menerima konteks yang relevan untuk domainnya, bukan user story mentah.

    Saat ini hanya RAG yang aktif. Untuk mengaktifkan agen lain, lihat komentar
    '# <-- UNCOMMENT' di file orchestrator.py.

    Args:
        requirement: Requirement dari GitLab issue atau user story
        include_api: (Deprecated) Digantikan oleh Planner LLM routing
        include_design: (Deprecated) Digantikan oleh Planner LLM routing
        include_kotlin_docs: (Deprecated) Tidak digunakan
        include_company_guidelines: (Deprecated) Digantikan oleh Planner LLM routing
    """
    logger.info("===== START PLANNER-EXECUTOR WORKFLOW =====")
    logger.info("Requirement (first 100 chars): %s", requirement[:100])

    # Log deprecation notice untuk boolean params
    if any([not include_api, include_design, not include_company_guidelines]):
        logger.warning(
            "Boolean params (include_api, include_design, dll) sekarang di-bypass. "
            "Planner LLM yang menentukan routing."
        )

    initial_state: OrchestratorState = {
        "requirement": requirement,
        "agent_plan": {},
        "code_structure": None,
        "api_contracts": None,
        "design_context": None,
        "company_guidelines": None,
        "errors": [],
        "consolidated_output": None,
    }

    result = await orchestrator_graph.ainvoke(initial_state)

    logger.info("===== PLANNER-EXECUTOR WORKFLOW DONE =====")
    return result.get("consolidated_output", json.dumps({"error": "No output produced"}, indent=2))


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

    results["orchestrator_mode"] = "Planner-Executor (Context Engineering)"

    return json.dumps(results, indent=2, ensure_ascii=False)


# ============================================================
# Entry Point
# ============================================================

if __name__ == "__main__":
    logger.info(
        "\nINTEGRATION ORCHESTRATOR -- Planner-Executor Architecture\n"
        "Mode: Planner LLM (Context Engineering) + LangGraph dynamic routing\n"
        "Aktif: RAG only (lihat '# <-- UNCOMMENT' untuk mengaktifkan agen lain)\n\n"
        "Tools:\n"
        "  - get_complete_integration_context() -- main flow (Planner→Executor)\n"
        "  - query_rag_directly()              -- RAG query langsung\n"
        "  - health_check_all_servers()         -- status check\n"
    )
    mcp.run(transport="stdio")