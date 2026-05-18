import os
import logging

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

from fastmcp import FastMCP

from src.config.settings import settings

logger = logging.getLogger("context7_server")

MCP_CONFIG = {
    "context7": {
        "command": "npx.cmd" if os.name == "nt" else "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "transport": "stdio",
    }
}

SYSTEM_PROMPT = (
    "You are a helpful Kotlin documentation assistant. "
    "Use the Context7 MCP tools to fetch accurate, up-to-date Kotlin documentation. "
    "Always call 'resolve-library-id' first to get the Kotlin library ID, "
    "then call 'get-library-docs' or 'query-docs' to retrieve the actual documentation. "
    "Provide clear explanations with code examples when available."
)

mcp = FastMCP(
    name="Context7AgentServer",
    instructions=(
        "Gunakan tool search_kotlin_documentation untuk mencari sintaks, "
        "library, atau arsitektur terbaru terkait Kotlin dan Android."
    ),
)

docs_llm = ChatOpenAI(
    model=settings.model_name,
    temperature=0.0,
    api_key=settings.openrouter_api_key,
    base_url=settings.openrouter_base_url,
    default_headers={"HTTP-Referer": "https://github.com/", "X-Title": "Kotlin Doc Agent"},
)


@mcp.tool()
async def search_kotlin_documentation(query: str) -> str:
    """
    Mencari dokumentasi terbaru dari framework Kotlin, Android, Jetpack Compose.

    Args:
        query: Pertanyaan dokumentasi teknis
    """
    try:
        async with MultiServerMCPClient(MCP_CONFIG) as mcp_client:
            tools = await mcp_client.get_tools()

            agent = create_agent(
                model=docs_llm,
                tools=tools,
                system_prompt=SYSTEM_PROMPT,
            )

            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": query}]
            })

            last_msg = response["messages"][-1]
            return last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    except Exception as e:
        return f"Terjadi kesalahan saat mencari dokumentasi: {e}"


if __name__ == "__main__":
    logger.info("Starting Context7 MCP Server (Transport STDIO)")
    mcp.run(transport="stdio")