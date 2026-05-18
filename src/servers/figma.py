import os
import sys
import json
import argparse
import functools
import logging
from typing import Optional, Any

from fastmcp import FastMCP
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_core.tools import tool as lc_tool
from langchain.agents import create_agent

from src.config.settings import settings
from src.models.schemas import FigmaDesignAnalysis
from src.utils.error_handler import wrap_async_tool_call
from src.utils.llm_factory import execute_agent_and_structure

logger = logging.getLogger("figma_server")

MCP_CONFIG = {
    "figma_source": {
        "command": "npx.cmd" if os.name == "nt" else "npx",
        "args": ["-y", "mcp-remote", settings.figma_mcp_url],
        "transport": "stdio",
    }
}

mcp = FastMCP(
    name="FigmaContextAgent",
    instructions=(
        "Saya adalah Context Agent untuk desain Figma. "
        "Tugas saya adalah mengekstrak metadata XML dan spesifikasi desain "
        "untuk membantu implementasi UI di proyek Android."
    ),
)


def _parse_mcp_result(result: Any) -> str:
    if isinstance(result, list):
        parts = []
        for item in result:
            if hasattr(item, "text"):
                parts.append(item.text)
            elif isinstance(item, dict) and "text" in item:
                parts.append(item["text"])
            else:
                parts.append(str(item))
        return "\n\n".join(parts)
    return str(result)


@mcp.tool()
@wrap_async_tool_call
async def get_figma_xml_metadata(node_id: str) -> str:
    """
    Mengambil metadata XML dari node Figma tertentu.

    Args:
        node_id: ID node Figma (contoh: '2335:5715' atau '123-456')
    """
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    metadata_tool = next((t for t in tools if "get_metadata" in t.name), None)
    if not metadata_tool:
        return "Tool 'get_metadata' tidak ditemukan di Figma MCP Server."

    result = await metadata_tool.ainvoke({"nodeId": node_id})
    return _parse_mcp_result(result)


@mcp.tool()
@wrap_async_tool_call
async def get_figma_design_context(node_id: str) -> str:
    """
    Mengambil konteks desain lengkap (metadata, screenshot, reference code)
    untuk sebuah node Figma.

    Args:
        node_id: ID node Figma
    """
    client = MultiServerMCPClient(MCP_CONFIG)
    tools = await client.get_tools()
    context_tool = next((t for t in tools if "get_design_context" in t.name), None)
    if not context_tool:
        return "Tool 'get_design_context' tidak ditemukan di Figma MCP Server."

    result = await context_tool.ainvoke({"nodeId": node_id})
    return _parse_mcp_result(result)


SYSTEM_PROMPT_FIGMA = (
    "Anda adalah 'The Figma Analyst', spesialis dalam konversi desain Figma ke XML metadata.\n"
    "Tugas utama Anda:\n"
    "1. Cari node desain yang paling cocok dengan fitur yang ditanyakan user.\n"
    "2. Ekstrak metadata XML lengkap untuk node tersebut menggunakan tool 'get_metadata'.\n"
    "3. Berikan output XML yang valid dan detail agar developer bisa langsung mengimplementasikannya ke Android.\n\n"
    "Gunakan 'get_metadata' tanpa nodeId terlebih dahulu untuk memetakan halaman, "
    "lalu panggil lagi dengan nodeId spesifik untuk mendapatkan detail XML-nya."
)


@mcp.tool()
async def run_figma_analyst_agent(user_query: str) -> FigmaDesignAnalysis:
    """
    Menjalankan agen kompeten yang mengerti desain Figma untuk menganalisis project.
    """
    llm = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=0.0,
    )

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
                design_notes="Figma MCP source returned no tools.",
            )

        figma_tools = []
        for t in raw_tools:
            clean_name = t.name.split("__")[-1] if "__" in t.name else t.name

            def create_tool_func(target_tool):
                async def tool_func(nodeId: str = ""):
                    return await target_tool.ainvoke({"nodeId": nodeId})
                return tool_func

            new_tool = lc_tool(create_tool_func(t))
            new_tool.name = clean_name
            new_tool.description = t.description
            figma_tools.append(new_tool)

        memory = MemorySaver()
        agent_executor = create_agent(
            llm,
            figma_tools,
            system_prompt=SYSTEM_PROMPT_FIGMA,
            name="FigmaAnalyst",
            checkpointer=memory,
        )

        logger.info("Figma Agent analyzing: '%s'...", user_query)

        final_output = ""
        config = {"configurable": {"thread_id": "figma_session_1"}}

        for chunk in agent_executor.stream(
            {"messages": [("human", user_query)]},
            config=config,
            stream_mode="updates",
        ):
            for node_name, node_update in chunk.items():
                if "messages" in node_update:
                    last_msg = node_update["messages"][-1]
                    if hasattr(last_msg, "content") and last_msg.content:
                        final_output = last_msg.content

        if not final_output:
            return FigmaDesignAnalysis(
                feature_name="Not Found",
                node_id="None",
                structure_summary="Agen tidak menemukan informasi desain yang relevan.",
                key_components=[],
                xml_context="",
                design_notes="Query tidak menghasilkan output dari desain figma.",
            )

        logger.info("Figma Agent analysis complete. Structuring output...")

        llm_structured = llm.with_structured_output(FigmaDesignAnalysis)
        result = llm_structured.invoke(final_output)
        return result

    except Exception as e:
        return FigmaDesignAnalysis(
            feature_name="Exception",
            node_id="Error",
            structure_summary=f"Terjadi kesalahan: {e}",
            key_components=[],
            xml_context="",
            design_notes="Pastikan Figma Desktop App dan Dev Mode aktif",
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Figma Context Agent")
    parser.add_argument("query", nargs="?", default="login", help="Nama layar atau node ID")
    parser.add_argument("--node", type=str, default=None, help="Override Node ID")
    parser.add_argument("--server", action="store_true", help="Jalankan sebagai MCP Server")
    args, _ = parser.parse_known_args()

    is_piped = not sys.stdin.isatty()

    if args.server or is_piped:
        logger.info("Starting MCP Server | Figma Source: %s", settings.figma_mcp_url)
        mcp.run(transport="stdio")
    else:
        import asyncio

        KNOWN_NODES = {
            "login": "2335:6376",
            "register": "2335:6404",
            "chat": "2335:5716",
            "home": "2335:5799",
        }

        node_id = args.node or KNOWN_NODES.get(args.query.lower(), args.query)
        logger.info("Test mode: mengambil XML untuk node '%s'", node_id)

        async def fast_test():
            result_xml = await get_figma_xml_metadata(node_id)
            print(result_xml)

        asyncio.run(fast_test())