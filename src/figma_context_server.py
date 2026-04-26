import os
import sys
import json
import functools
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

from fastmcp import FastMCP
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent
from langchain_core.tools import tool

load_dotenv()

# ──────────────────────────────────────────────
# Konfigurasi
# ──────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o")

# Figma MCP Server Config (via mcp-remote bridge for stability)
FIGMA_MCP_URL = "http://127.0.0.1:3845/sse"

MCP_CONFIG = {
    "figma_source": {
        "command": "npx.cmd" if os.name == "nt" else "npx",
        "args": ["-y", "mcp-remote", FIGMA_MCP_URL],
        "transport": "stdio",
    }
}

# ──────────────────────────────────────────────
# FastMCP initialization
# ──────────────────────────────────────────────
mcp = FastMCP(
    name="FigmaContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk desain Figma. "
        "Tugas saya adalah mengekstrak metadata XML dan spesifikasi desain "
        "untuk membantu implementasi UI di proyek Android."
    ),
)

# Dekorator kustom untuk menangkap error
def wrap_tool_call(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except ConnectionRefusedError:
            return "❌ Gagal terhubung ke Figma MCP (Port 3845). Pastikan Figma Desktop App terbuka dan Dev Mode aktif."
        except Exception as e:
            error_msg = f"Error executing tool '{func.__name__}': {str(e)}"
            if "mcp-remote" in error_msg:
                return "❌ Gagal menjalankan bridge 'mcp-remote'. Pastikan 'npx' dapat diakses dan Figma bridge tersedia."
            print(f"❌ [Figma Tool Error] {error_msg}", file=sys.stderr)
            return error_msg
    return wrapper

# ══════════════════════════════════════════════
# MCP TOOLS
# ══════════════════════════════════════════════

@mcp.tool()
@wrap_tool_call
async def get_figma_xml_metadata(node_id: str) -> str:
    """
    Mengambil metadata XML dari node Figma tertentu.
    XML ini berisi struktur layer, nama, posisi, dan ukuran.

    Args:
        node_id: ID node Figma (contoh: '2335:5715' atau '123-456').
    """
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    # Find get_metadata tool
    metadata_tool = next((t for t in tools if "get_metadata" in t.name), None)
    if not metadata_tool:
        return "❌ Tool 'get_metadata' tidak ditemukan di Figma MCP Server."
    
    result = await metadata_tool.ainvoke({"nodeId": node_id})
    return str(result)

@mcp.tool()
@wrap_tool_call
async def get_figma_design_context(node_id: str) -> str:
    """
    Mengambil konteks desain lengkap (metadata, screenshot, reference code)
    untuk sebuah node Figma.

    Args:
        node_id: ID node Figma.
    """
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    context_tool = next((t for t in tools if "get_design_context" in t.name), None)
    if not context_tool:
        return "❌ Tool 'get_design_context' tidak ditemukan di Figma MCP Server."
    
    result = await context_tool.ainvoke({"nodeId": node_id})
    return str(result)

# ──────────────────────────────────────────────
# 2. Inisialisasi Agen (The Figma Analyst)
# ──────────────────────────────────────────────

from pydantic import BaseModel, Field, ConfigDict

class FigmaDesignAnalysis(BaseModel):
    """Skema hasil analisis desain Figma."""
    model_config = ConfigDict(extra="forbid")
    
    feature_name: str = Field(description="Nama fitur atau halaman yang dianalisis.")
    node_id: str = Field(description="ID node utama yang dianalisis.")
    structure_summary: str = Field(description="Ringkasan struktur UI (XML).")
    key_components: List[Dict[str, str]] = Field(description="Daftar komponen penting (button, input, dll) dan ID-nya.")
    xml_context: str = Field(description="Potongan XML metadata yang paling relevan.")
    design_notes: Optional[str] = Field(description="Catatan tambahan mengenai desain atau styling.")

@mcp.tool()
async def run_figma_analyst_agent(user_query: str) -> FigmaDesignAnalysis:
    """
    Menjalankan agen kompeten yang mengerti desain Figma untuk menganalisis project.
    Gunakan ini untuk mencari node yang relevan dengan sebuah fitur dan mengekstrak XML-nya.
    """
    llm = ChatOpenAI(
        model=MODEL_NAME,
        api_key=API_KEY,
        base_url=BASE_URL,
        temperature=0.0,
    )
    
    # Prompt untuk Sang Analis Figma (Fokus pada XML)
    system_instructions = (
        "Anda adalah 'The Figma Analyst', spesialis dalam konversi desain Figma ke XML metadata.\n"
        "Tugas utama Anda:\n"
        "1. Cari node desain yang paling cocok dengan fitur yang ditanyakan user.\n"
        "2. Ekstrak metadata XML lengkap untuk node tersebut menggunakan tool 'get_metadata'.\n"
        "3. Berikan output XML yang valid dan detail agar developer bisa langsung mengimplementasikannya ke Android.\n\n"
        "Gunakan 'get_metadata' tanpa nodeId terlebih dahulu untuk memetakan halaman, "
        "lalu panggil lagi dengan nodeId spesifik untuk mendapatkan detail XML-nya."
    )
    
    # Kita butuh client untuk mengambil tools dari Figma MCP Server
    try:
        figma_client = MultiServerMCPClient(MCP_CONFIG)
        raw_tools = await figma_client.get_tools()
        
        if not raw_tools:
            return FigmaDesignAnalysis(
                feature_name="Error",
                node_id="None",
                structure_summary="Gagal mengambil tools dari Figma MCP. Pastikan Figma terbuka.",
                key_components=[],
                xml_context="",
                design_notes="Figma MCP source returned no tools."
            )
        
        # NORMALISASI: Hapus prefix 'figma_source__' agar LLM bisa memanggil tool dengan nama aslinya
        from langchain_core.tools import Tool
        figma_tools = []
        for t in raw_tools:
            # Jika nama tool mengandung prefix (misal 'figma_source__get_metadata')
            clean_name = t.name.split("__")[-1] if "__" in t.name else t.name
            
            # Buat tool baru dengan nama bersih
            new_tool = tool(clean_name)(t._run if hasattr(t, '_run') else t.func)
            new_tool.description = t.description
            figma_tools.append(new_tool)
        
        # Buat ReAct Agent
        from langgraph.prebuilt import create_react_agent
        from langgraph.checkpoint.memory import MemorySaver
        
        memory = MemorySaver()
        agent_executor = create_react_agent(
            llm, 
            figma_tools, 
            state_modifier=system_instructions,
            checkpointer=memory
        )
        
        print(f"\n🎨 [Figma Agent] Analyzing design for: '{user_query}'...", file=sys.stderr)
        
        config = {"configurable": {"thread_id": "figma_session_1"}}
        final_output = ""
        
        async for chunk in agent_executor.astream(
            {"messages": [("human", user_query)]}, 
            config=config,
            stream_mode="updates"
        ):
            for node_name, node_update in chunk.items():
                if "messages" in node_update:
                    last_msg = node_update["messages"][-1]
                    if hasattr(last_msg, 'content') and last_msg.content:
                        final_output = last_msg.content
        
        if not final_output:
            return FigmaDesignAnalysis(
                feature_name="Not Found",
                node_id="None",
                structure_summary="Agen tidak menemukan informasi desain yang relevan.",
                key_components=[],
                xml_context="",
                design_notes="Query tidak menghasilkan output dari desain figma."
            )

        print(f"✅ [Figma Agent] Analysis complete.", file=sys.stderr)
        
        # Konversi ke Structured Output
        llm_structured = llm.with_structured_output(FigmaDesignAnalysis)
        try:
            structured_result = llm_structured.invoke(final_output)
            return structured_result
        except Exception as pydantic_err:
            print(f"⚠️ [Figma Agent] Structured output conversion failed: {str(pydantic_err)}", file=sys.stderr)
            return FigmaDesignAnalysis(
                feature_name="Manual Parse Needed",
                node_id="Unknown",
                structure_summary=final_output[:500] + "...",
                key_components=[],
                xml_context="",
                design_notes=f"Parsing error: {str(pydantic_err)}"
            )
    except Exception as e:
        return FigmaDesignAnalysis(
            feature_name="Exception",
            node_id="Error",
            structure_summary=f"Terjadi kesalahan: {str(e)}",
            key_components=[],
            xml_context="",
            design_notes="Pastikan Figma Desktop App dan Dev Mode aktif di http://127.0.0.1:3845/sse"
        )

# ══════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    print(
        f"[Figma Context Agent] 🚀 Memulai MCP Server...\n"
        f"   Figma Source: {FIGMA_MCP_URL}\n"
        f"   Tools       : get_figma_xml_metadata\n"
        f"                 get_figma_design_context\n"
        f"                 run_figma_analyst_agent [AGENT]\n",
        file=sys.stderr
    )
    mcp.run(transport="stdio")
