import os
import sys
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from fastmcp import FastMCP

load_dotenv()

# 1. Konfigurasi
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o")

if not API_KEY:
    print("❌ [WARNING] OPENROUTER_API_KEY belum diset.", file=sys.stderr)

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

# 2. Inisialisasi Server & LLM Instance (Di luar fungsi agar efisien)
mcp = FastMCP(
    name="Context7AgentServer",
    instructions=(
        "Gunakan tool search_kotlin_documentation untuk mencari sintaks, "
        "library, atau arsitektur terbaru terkait Kotlin dan Android."
    )
)

# LLM Instance dibuat sekali (Singleton pattern)
docs_llm = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0.0,
    api_key=API_KEY,
    base_url=BASE_URL,
    default_headers={"HTTP-Referer": "https://github.com/", "X-Title": "Kotlin Doc Agent"},
)

# 3. Definisi Tool yang diekspos ke Android Studio
@mcp.tool()
async def search_kotlin_documentation(query: str) -> str:
    """
    Mencari dokumentasi terbaru dari framework Kotlin, Android, Jetpack Compose.
    
    Args:
        query: Pertanyaan dokumentasi teknis (contoh: "Jetpack Compose Navigation in Kotlin")
    """
    try:
        # Menjalankan npx upstash/context7
        async with MultiServerMCPClient(MCP_CONFIG) as mcp_client:
            tools = await mcp_client.get_tools()
            
            # Bangun ReAct Agent (The Knowledge Retriever)
            agent = create_react_agent(
                model=docs_llm,
                tools=tools,
                prompt=SYSTEM_PROMPT,
            )
            
            # Eksekusi agen untuk mencari jawaban di internet
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": query}]
            })
            
            last_msg = response["messages"][-1]
            return last_msg.content if hasattr(last_msg, "content") else str(last_msg)

    except Exception as e:
        return f"❌ Terjadi kesalahan saat Agent mencari dokumentasi: {str(e)}"

# 4. Entry Point
if __name__ == "__main__":
    print("[Agent 3: Context7 Server] 🚀 Memulai MCP Server (Transport STDIO)...", file=sys.stderr)
    mcp.run(transport="stdio")