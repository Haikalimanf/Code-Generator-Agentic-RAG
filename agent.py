import asyncio
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
import mcp

load_dotenv()

# ─────────────────────────────────────────────────────────────
# Konfigurasi — baca dari .env
# ─────────────────────────────────────────────────────────────
API_KEY    = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL   = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o-mini")

if not API_KEY or API_KEY == "your_openrouter_api_key_here":
    raise ValueError(
        "❌ OPENROUTER_API_KEY belum diset.\n"
        "   Buka file .env dan isi dengan API key OpenRouter kamu.\n"
        "   Daftar / lihat key di: https://openrouter.ai/keys"
    )

# ─────────────────────────────────────────────────────────────
# MCP Server Configuration — Context7
# ─────────────────────────────────────────────────────────────
MCP_CONFIG = {
    "context7": {
        "command": "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "transport": "stdio",
    }
}

# ─────────────────────────────────────────────────────────────
# Kotlin Documentation Queries (dijalankan saat startup)
# ─────────────────────────────────────────────────────────────
KOTLIN_QUERIES = [
    "Fetch Kotlin documentation for coroutines and how to use them with async/await pattern",
    "Fetch Kotlin documentation for data classes and their usage",
    "Fetch Kotlin documentation for extension functions",
]

SYSTEM_PROMPT = (
    "You are a helpful Kotlin documentation assistant. "
    "Use the Context7 MCP tools to fetch accurate, up-to-date Kotlin documentation. "
    "Always call 'resolve-library-id' first to get the Kotlin library ID, "
    "then call 'get-library-docs' or 'query-docs' to retrieve the actual documentation. "
    "Provide clear explanations with code examples when available."
)

@mcp.tool()
async def run_agent(query: str, agent, verbose: bool = True) -> str:
    """Jalankan agent dengan query dan kembalikan response."""
    if verbose:
        print(f"\n{'='*60}")
        print(f"📝 Query: {query}")
        print("=" * 60)

    try:
        response = await agent.ainvoke({
            "messages": [{"role": "user", "content": query}]
        })
        # Ambil pesan terakhir dari agent
        last_msg = response["messages"][-1]
        result = last_msg.content if hasattr(last_msg, "content") else str(last_msg)
    except Exception as e:
        result = f"❌ Error: {e}"

    if verbose:
        print(f"\n🤖 Response:\n{result}")

    return result


async def main():
    print("🚀 Starting Kotlin Documentation Agent with MCP Context7")
    print("=" * 60)

    # ── Inisialisasi LLM via OpenRouter ───────────────────────────
    llm = ChatOpenAI(
        model=MODEL_NAME,
        temperature=0,
        api_key=API_KEY,
        base_url=BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/kotlin-doc-agent",
            "X-Title": "Kotlin Doc Agent",
        },
    )
    print(f"✅ LLM    : {MODEL_NAME}")
    print(f"   URL    : {BASE_URL}")

    # ── Koneksi ke Context7 MCP ───────────────────────────────────
    print("\n⏳ Menghubungkan ke Context7 MCP server...")
    mcp_client = MultiServerMCPClient(MCP_CONFIG)
    tools = await mcp_client.get_tools()

    print(f"✅ Terhubung — {len(tools)} tools tersedia:")
    for tool in tools:
        print(f"   • {tool.name}: {tool.description[:70]}...")

    # ── Bangun ReAct Agent (LangGraph) ────────────────────────────
    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )

    print("\n🤖 Agent siap! Mulai mengambil dokumentasi Kotlin...\n")

    # ── Jalankan query awal ───────────────────────────────────────
    results = []
    for query in KOTLIN_QUERIES:
        result = await run_agent(query, agent)
        results.append(result)

    print("\n" + "=" * 60)
    print(f"📚 SELESAI — {len(results)} query berhasil diproses")
    print("=" * 60)

    # ── Mode Interaktif ───────────────────────────────────────────
    print("\n💬 Mode Interaktif — ketik 'exit' untuk keluar\n")
    while True:
        try:
            user_input = input("Ask about Kotlin: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 Goodbye!")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("👋 Goodbye!")
            break
        if not user_input:
            continue

        await run_agent(user_input, agent)


if __name__ == "__main__":
    asyncio.run(main())