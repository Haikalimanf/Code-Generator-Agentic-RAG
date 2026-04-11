import asyncio
import sys
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from fastmcp import FastMCP

load_dotenv()

# ─────────────────────────────────────────────────────────────
# Inisialisasi Server FastMCP
# ─────────────────────────────────────────────────────────────
mcp = FastMCP(
    name="Context7AgentServer",
    instructions=(
        "Anda adalah asisten dokumentasi Kotlin. Anda memiliki "
        "koneksi ke internet melalui Context7. Gunakan kemampuan saya "
        "untuk mencari dokumentasi terbaru Kotlin/Android."
    )
)

# ─────────────────────────────────────────────────────────────
# Konfigurasi — baca dari .env
# ─────────────────────────────────────────────────────────────
API_KEY    = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL   = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

if not API_KEY or API_KEY == "your_openrouter_api_key_here":
    print("❌ [WARNING] OPENROUTER_API_KEY belum diset. Server mungkin gagal.", file=sys.stderr)

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

# ─────────────────────────────────────────────────────────────
# MCP Tools
# ─────────────────────────────────────────────────────────────
@mcp.tool()
async def search_kotlin_documentation(query: str) -> str:
    """
    Tanyakan dokumentasi terbaru dari framework Kotlin, Android, Jetpack Compose, dll.
    Agent AI terpisah akan meriset dan memberikan hasil bacaan dokumentasinya ke Anda.
    
    Args:
        query: Pertanyaan dokumentasi, misalnya "coroutine async await example"
    """
    try:
        # Inisialisasi LLM
        llm = ChatOpenAI(
            model=MODEL_NAME,
            temperature=0,
            api_key=API_KEY,
            base_url=BASE_URL,
            default_headers={"HTTP-Referer": "https://github.com/", "X-Title": "Kotlin Doc Agent"},
        )

        # Menjalankan npx upstash/context7 sebentar secara background
        async with MultiServerMCPClient(MCP_CONFIG) as mcp_client:
            tools = await mcp_client.get_tools()
            
            # Bangun ReAct Agent (LangGraph)
            agent = create_react_agent(
                model=llm,
                tools=tools,
                prompt=SYSTEM_PROMPT,
            )
            
            # Agent LangGraph memproses pertanyaan
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": query}]
            })
            
            # Ekstrak hasil bacaan AI
            last_msg = response["messages"][-1]
            return last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    except Exception as e:
        return f"❌ Terjadi kesalahan saat Agent mencari dokumentasi: {e}"

# ─────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("[Context7 Agent] 🚀 Memulai MCP Server (Transport STDIO)...", file=sys.stderr)
    mcp.run(transport="stdio")