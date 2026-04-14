import os
import sys
import asyncio
from typing import Dict, List, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from fastmcp import FastMCP

load_dotenv()

# ==================== KONFIGURASI ====================
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o")

if not API_KEY:
    print("❌ [WARNING] OPENROUTER_API_KEY belum diset.", file=sys.stderr)

# Konfigurasi Multi-MCP Servers
MCP_SERVERS_CONFIG = {
    # Server 1: Postman API Context
    "postman": {
        "command": "python" if os.name == "nt" else "python3",
        "args": [r"D:\RAG\Membuat MCP Server\src\postman_context_server.py"],
        "transport": "stdio",
        "env": {
            "POSTMAN_API_KEY": os.getenv("POSTMAN_API_KEY", ""),
            "WORKSPACE_ID": os.getenv("WORKSPACE_ID", "")
        }
    },
    
    # Server 2: Android Studio Context
    "android_studio": {
        "command": "uv" if os.name != "nt" else "uv.exe",
        "args": [
            "--directory",
            r"D:\RAG\Membuat MCP Server\src\agent_context_android_studio.py",  # Sesuaikan path Anda
            "run",
            "agent_context_android_studio.py"
        ],
        "transport": "stdio",
    },
    
    # Server 3: Context7 (Kotlin Docs)
    "context7": {
        "command": "npx.cmd" if os.name == "nt" else "npx",
        "args": ["-y", "@upstash/context7-mcp@latest"],
        "transport": "stdio",
    }
}

ORCHESTRATOR_PROMPT = """
You are an Integration Orchestrator for Android development code generation.

Your role is to intelligently coordinate three specialized MCP servers:
1. **Postman MCP**: Fetch API endpoints, schemas, and request/response contracts
2. **Android Studio MCP**: Get current code structure, open files, and project context
3. **Context7 MCP**: Retrieve latest Kotlin/Android documentation updates

WORKFLOW RULES:
- Always start with Android Studio context to understand current code structure
- Query Postman ONLY if API integration is mentioned in requirements
- Query Context7 ONLY if there's uncertainty about Kotlin syntax or new features
- Provide structured output in JSON format with clear sections

OUTPUT FORMAT:
{
  "api_contracts": {...},  // From Postman (if applicable)
  "code_structure": {...}, // From Android Studio
  "kotlin_updates": {...}, // From Context7 (if needed)
  "recommendations": [...]
}

Be concise, technical, and actionable.
"""

# ==================== LLM INSTANCE ====================
orchestrator_llm = ChatOpenAI(
    model=MODEL_NAME,
    temperature=0.0,
    api_key=API_KEY,
    base_url=BASE_URL,
    default_headers={
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Integration Orchestrator"
    },
)

# ==================== MCP SERVER ORCHESTRATOR ====================
mcp = FastMCP(
    name="IntegrationOrchestrator",
    instructions="Orchestrates Postman, Android Studio, and Context7 MCP servers for code generation"
)


@mcp.tool()
async def get_complete_integration_context(
    requirement: str,
    include_api: bool = True,
    include_kotlin_docs: bool = False
) -> str:
    """
    Mengambil konteks lengkap dari ketiga MCP server secara terkoordinasi.
    
    Args:
        requirement: Requirement dari GitLab issue (e.g., "Implement user login with JWT")
        include_api: Apakah perlu query Postman untuk API contracts
        include_kotlin_docs: Apakah perlu query Context7 untuk Kotlin updates
    
    Returns:
        JSON string dengan aggregated context dari semua servers
    """
    print(f"\n🎯 [Orchestrator] Processing requirement: {requirement}", file=sys.stderr)
    
    results = {
        "requirement": requirement,
        "api_contracts": None,
        "code_structure": None,
        "kotlin_updates": None,
        "errors": []
    }
    
    # Task definitions untuk parallel execution
    async def fetch_android_studio_context():
        """Selalu dijalankan - core context"""
        try:
            print("📱 [Orchestrator] Fetching Android Studio context...", file=sys.stderr)
            async with MultiServerMCPClient({"android_studio": MCP_SERVERS_CONFIG["android_studio"]}) as client:
                tools = await client.get_tools()
                agent = create_react_agent(orchestrator_llm, tools, prompt="Get current project structure and open files")
                
                response = await agent.ainvoke({
                    "messages": [{"role": "user", "content": f"Analyze project context for: {requirement}"}]
                })
                results["code_structure"] = response["messages"][-1].content
                print("✅ [Orchestrator] Android Studio context retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Android Studio MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    async def fetch_postman_api():
        """Conditional - hanya jika include_api=True"""
        if not include_api:
            print("⏭️  [Orchestrator] Skipping Postman (not needed)", file=sys.stderr)
            return
            
        try:
            print("🌐 [Orchestrator] Fetching Postman API contracts...", file=sys.stderr)
            async with MultiServerMCPClient({"postman": MCP_SERVERS_CONFIG["postman"]}) as client:
                tools = await client.get_tools()
                agent = create_react_agent(orchestrator_llm, tools, prompt="Fetch relevant API endpoints and schemas")
                
                response = await agent.ainvoke({
                    "messages": [{"role": "user", "content": f"Find API endpoints for: {requirement}"}]
                })
                results["api_contracts"] = response["messages"][-1].content
                print("✅ [Orchestrator] Postman API contracts retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Postman MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    async def fetch_kotlin_docs():
        """Conditional - hanya jika include_kotlin_docs=True"""
        if not include_kotlin_docs:
            print("⏭️  [Orchestrator] Skipping Context7 (no Kotlin updates needed)", file=sys.stderr)
            return
            
        try:
            print("📚 [Orchestrator] Checking latest Kotlin documentation...", file=sys.stderr)
            async with MultiServerMCPClient({"context7": MCP_SERVERS_CONFIG["context7"]}) as client:
                tools = await client.get_tools()
                agent = create_react_agent(orchestrator_llm, tools, prompt=ORCHESTRATOR_PROMPT)
                
                response = await agent.ainvoke({
                    "messages": [{"role": "user", "content": f"Check Kotlin syntax updates for: {requirement}"}]
                })
                results["kotlin_updates"] = response["messages"][-1].content
                print("✅ [Orchestrator] Kotlin docs retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Context7 MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    # Execute tasks in parallel untuk efisiensi
    await asyncio.gather(
        fetch_android_studio_context(),
        fetch_postman_api(),
        fetch_kotlin_docs(),
        return_exceptions=True  # Continue even if one fails
    )
    
    # Format final output
    import json
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
async def query_specific_server(
    server_name: str,
    query: str
) -> str:
    """
    Query satu MCP server spesifik (untuk debugging atau targeted queries).
    
    Args:
        server_name: Pilih dari 'postman', 'android_studio', atau 'context7'
        query: Pertanyaan spesifik untuk server tersebut
    """
    if server_name not in MCP_SERVERS_CONFIG:
        return f"❌ Invalid server name. Choose from: {list(MCP_SERVERS_CONFIG.keys())}"
    
    try:
        print(f"🔍 [Orchestrator] Querying {server_name}...", file=sys.stderr)
        async with MultiServerMCPClient({server_name: MCP_SERVERS_CONFIG[server_name]}) as client:
            tools = await client.get_tools()
            agent = create_react_agent(orchestrator_llm, tools, prompt=f"You are a {server_name} specialist")
            
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": query}]
            })
            return response["messages"][-1].content
    except Exception as e:
        return f"❌ Error querying {server_name}: {str(e)}"


@mcp.tool()
async def health_check_all_servers() -> str:
    """
    Melakukan health check ke semua MCP servers untuk memastikan mereka online.
    """
    results = {}
    
    for server_name, config in MCP_SERVERS_CONFIG.items():
        try:
            print(f"🏥 [Health Check] Testing {server_name}...", file=sys.stderr)
            async with MultiServerMCPClient({server_name: config}) as client:
                tools = await client.get_tools()
                results[server_name] = {
                    "status": "✅ ONLINE",
                    "tools_count": len(tools),
                    "available_tools": [tool.name for tool in tools]
                }
        except Exception as e:
            results[server_name] = {
                "status": "❌ OFFLINE",
                "error": str(e)
            }
    
    import json
    return json.dumps(results, indent=2)


# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║   🎭 INTEGRATION ORCHESTRATOR - MCP Multi-Server Agent   ║
    ║                                                           ║
    ║   Mengelola 3 MCP Servers:                               ║
    ║   • Postman API Context                                  ║
    ║   • Android Studio Context                               ║
    ║   • Context7 (Kotlin Docs)                               ║
    ╚═══════════════════════════════════════════════════════════╝
    """, file=sys.stderr)
    
    mcp.run(transport="stdio")