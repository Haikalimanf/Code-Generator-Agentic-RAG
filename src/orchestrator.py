import os
import sys
import asyncio
import json
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from fastmcp import FastMCP

# ==================== LOAD RAG CHAIN LANGSUNG ====================
RAG_ERROR_DETAIL = None
try:
    from agent_pdf_rag import rag_chain
    RAG_AVAILABLE = True
    print("✅ RAG Chain loaded successfully", file=sys.stderr)
except ImportError as e:
    RAG_AVAILABLE = False
    RAG_ERROR_DETAIL = str(e)
    print(f"⚠️  RAG Chain not available: {e}", file=sys.stderr)
    import traceback
    print(traceback.format_exc(), file=sys.stderr)
except Exception as e:
    RAG_AVAILABLE = False
    RAG_ERROR_DETAIL = f"Initialization error: {str(e)}"
    print(f"⚠️  RAG Chain initialization failed: {e}", file=sys.stderr)
    import traceback
    print(traceback.format_exc(), file=sys.stderr)

load_dotenv()

# ==================== DIAGNOSIS ENV VARIABLES ====================
print("🔍 [Orchestrator] Environment variables loaded:", file=sys.stderr)
print(f"    POSTMAN_API_KEY: {'✅ Set' if os.getenv('POSTMAN_API_KEY') else '❌ Not set'}", file=sys.stderr)
print(f"    POSTMAN_WORKSPACE_ID: {'✅ Set' if os.getenv('POSTMAN_WORKSPACE_ID') else '❌ Not set'}", file=sys.stderr)
print(f"    ANDROID_PROJECT_ROOT: {'✅ Set' if os.getenv('ANDROID_PROJECT_ROOT') else '❌ Not set'}", file=sys.stderr)
print(f"    CONTEXT7_API_KEY: {'✅ Set' if os.getenv('CONTEXT7_API_KEY') else '❌ Not set'}", file=sys.stderr)

# ==================== KONFIGURASI ====================
API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "openai/gpt-4o")

if not API_KEY:
    print("❌ [WARNING] OPENROUTER_API_KEY belum diset.", file=sys.stderr)

# Get project root dynamically from this file's location
PROJECT_ROOT = Path(__file__).parent.parent

# Get environment variables with validation
POSTMAN_API_KEY = os.getenv("POSTMAN_API_KEY", "").strip()
POSTMAN_WORKSPACE_ID = os.getenv("POSTMAN_WORKSPACE_ID", "").strip()
ANDROID_PROJECT_ROOT = os.getenv("ANDROID_PROJECT_ROOT", "").strip()
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY", "").strip()

# Path to Python executable - MUST use sys.executable to get uv-managed Python
# Using plain "python" would fail because packages are installed in uv's venv
PYTHON_CMD = sys.executable

# Konfigurasi Multi-MCP Servers (TANPA PDF RAG - sekarang direct access)
MCP_SERVERS_CONFIG = {}

# Only configure Postman if API key is present
if POSTMAN_API_KEY:
    MCP_SERVERS_CONFIG["postman"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "postman_context_server.py")],
        "transport": "stdio",
        "env": {
            **os.environ,  # Pass semua env vars agar .env terbaca
            "POSTMAN_API_KEY": POSTMAN_API_KEY,
            "POSTMAN_WORKSPACE_ID": POSTMAN_WORKSPACE_ID,
        }
    }

# Only configure Android Studio if project root is present
if ANDROID_PROJECT_ROOT and Path(ANDROID_PROJECT_ROOT).exists():
    MCP_SERVERS_CONFIG["android_studio"] = {
        "command": PYTHON_CMD,
        "args": [str(PROJECT_ROOT / "src" / "agent_context_android_studio.py")],
        "transport": "stdio",
        "env": {
            **os.environ,  # Pass semua env vars
            "ANDROID_PROJECT_ROOT": ANDROID_PROJECT_ROOT,
        }
    }

# Context7 doesn't require API key but we'll pass it if available
MCP_SERVERS_CONFIG["context7"] = {
    "command": "npx.cmd" if os.name == "nt" else "npx",
    "args": ["-y", "@upstash/context7-mcp@latest"],
    "transport": "stdio",
    "env": {
        **os.environ,  # Pass semua env vars termasuk PATH
        "CONTEXT7_API_KEY": CONTEXT7_API_KEY,
    }
}

# Debug: Show configured servers
print(f"🔧 [Orchestrator] Configured MCP servers: {list(MCP_SERVERS_CONFIG.keys())}", file=sys.stderr)
print(f"🔧 [Orchestrator] POSTMAN_API_KEY: {'Set' if POSTMAN_API_KEY else 'NOT SET'}", file=sys.stderr)
print(f"🔧 [Orchestrator] ANDROID_PROJECT_ROOT: {ANDROID_PROJECT_ROOT if ANDROID_PROJECT_ROOT else 'NOT SET'}", file=sys.stderr)

ORCHESTRATOR_PROMPT = """
You are an Integration Orchestrator for Android development code generation.

Your role is to intelligently coordinate multiple sources:
1. **Postman MCP**: Fetch API endpoints, schemas, and request/response contracts
2. **Android Studio MCP**: Get current code structure, open files, and project context
3. **Context7 MCP**: Retrieve latest Kotlin/Android documentation updates
4. **PDF RAG**: Access company documents, internal guidelines, and best practices (direct access)

WORKFLOW RULES:
- Always start with Android Studio context to understand current code structure
- Query Postman ONLY if API integration is mentioned in requirements
- Query Context7 ONLY if there's uncertainty about Kotlin syntax or new features
- Query RAG for company-specific guidelines, coding standards, and best practices
- Provide structured output in JSON format with clear sections

OUTPUT FORMAT:
{
  "api_contracts": {...},        // From Postman (if applicable)
  "code_structure": {...},       // From Android Studio
  "kotlin_updates": {...},       // From Context7 (if needed)
  "company_guidelines": {...},   // From PDF RAG (company docs, standards, practices)
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
    max_tokens=2048,
    default_headers={
        "HTTP-Referer": "https://github.com/",
        "X-Title": "Integration Orchestrator"
    },
)

# ==================== MCP SERVER ORCHESTRATOR ====================
mcp = FastMCP(
    name="IntegrationOrchestrator",
    instructions="Orchestrates Postman, Android Studio, Context7 MCP servers + direct RAG access for code generation"
)


@mcp.tool()
async def get_complete_integration_context(
    requirement: str,
    include_api: bool = True,
    include_kotlin_docs: bool = False,
    include_company_guidelines: bool = True
) -> str:
    """
    Mengambil konteks lengkap dari MCP servers + direct RAG access.
    
    Args:
        requirement: Requirement dari GitLab issue (e.g., "Implement user login with JWT")
        include_api: Query Postman untuk API contracts
        include_kotlin_docs: Query Context7 untuk Kotlin updates
        include_company_guidelines: Query RAG langsung untuk company guidelines
    
    Returns:
        JSON string dengan aggregated context dari semua sources
    """
    print(f"\n🎯 [Orchestrator] Processing requirement: {requirement}", file=sys.stderr)
    
    results = {
        "requirement": requirement,
        "api_contracts": None,
        "code_structure": None,
        "kotlin_updates": None,
        "company_guidelines": None,
        "errors": []
    }
    
    # ==================== TASK 1: Android Studio Context ====================
    async def fetch_android_studio_context():
        """Selalu dijalankan - core context"""
        if "android_studio" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Android Studio tidak dikonfigurasi (ANDROID_PROJECT_ROOT tidak ada)")
            return
        try:
            print("📱 [Orchestrator] Fetching Android Studio context...", file=sys.stderr)
            client = MultiServerMCPClient({"android_studio": MCP_SERVERS_CONFIG["android_studio"]})
            tools = await client.get_tools()
            agent = create_react_agent(orchestrator_llm, tools)
            
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": f"Analyze project context for: {requirement}"}]
            })
            results["code_structure"] = response["messages"][-1].content
            print("✅ [Orchestrator] Android Studio context retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Android Studio MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    # ==================== TASK 2: Postman API ====================
    async def fetch_postman_api():
        """Conditional - hanya jika include_api=True"""
        if not include_api:
            print("⏭️  [Orchestrator] Skipping Postman (not needed)", file=sys.stderr)
            return
        if "postman" not in MCP_SERVERS_CONFIG:
            results["errors"].append("Postman tidak dikonfigurasi (POSTMAN_API_KEY tidak ada)")
            return
        try:
            print("🌐 [Orchestrator] Fetching Postman API contracts...", file=sys.stderr)
            client = MultiServerMCPClient({"postman": MCP_SERVERS_CONFIG["postman"]})
            tools = await client.get_tools()
            agent = create_react_agent(orchestrator_llm, tools)

            # Kirim requirement dari GitLab ke Postman agent secara eksplisit
            # agar tool get_api_context_for_feature() bisa mencari endpoint yang relevan
            postman_prompt = (
                f"Cari API contract untuk fitur berikut dari GitLab issue:\n\n"
                f"{requirement}\n\n"
                f"Gunakan tool get_api_context_for_feature() dengan feature_description di atas "
                f"untuk mendapatkan endpoint, request body, dan response schema yang relevan."
            )
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": postman_prompt}]
            })
            results["api_contracts"] = response["messages"][-1].content
            print("✅ [Orchestrator] Postman API contracts retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Postman MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    # ==================== TASK 3: Kotlin Docs ====================
    async def fetch_kotlin_docs():
        """Conditional - hanya jika include_kotlin_docs=True"""
        if not include_kotlin_docs:
            print("⏭️  [Orchestrator] Skipping Context7 (no Kotlin updates needed)", file=sys.stderr)
            return
        try:
            print("📚 [Orchestrator] Checking latest Kotlin documentation...", file=sys.stderr)
            client = MultiServerMCPClient({"context7": MCP_SERVERS_CONFIG["context7"]})
            tools = await client.get_tools()
            agent = create_react_agent(orchestrator_llm, tools)
            
            response = await agent.ainvoke({
                "messages": [{"role": "user", "content": f"Check Kotlin syntax updates for: {requirement}"}]
            })
            results["kotlin_updates"] = response["messages"][-1].content
            print("✅ [Orchestrator] Kotlin docs retrieved", file=sys.stderr)
        except Exception as e:
            error_msg = f"Context7 MCP error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)

    # ==================== TASK 4: Company Guidelines (Direct RAG) ====================
    async def fetch_company_guidelines():
        """Query RAG chain langsung - TANPA MCP Server"""
        if not include_company_guidelines:
            print("⏭️  [Orchestrator] Skipping RAG (not needed)", file=sys.stderr)
            return
            
        if not RAG_AVAILABLE:
            error_msg = "RAG Chain tidak tersedia - pastikan VECTOR_DATABASE_URL dan credentials sudah diset"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
            return
            
        try:
            print("📚 [Orchestrator] Querying company documents via RAG...", file=sys.stderr)
            
            # Query RAG chain LANGSUNG (bukan via MCP)
            query_text = f"Berikan standar, best practices, dan guidelines untuk: {requirement}"
            response = rag_chain.invoke({"input": query_text})
            
            # Format hasil
            company_guidelines = response.get("answer", "No answer found")
            
            # Tambahkan referensi sumber jika ada
            if response.get("context"):
                company_guidelines += "\n\n📄 Sumber Referensi:\n"
                for i, doc in enumerate(response["context"], 1):
                    page = doc.metadata.get("page", "?")
                    company_guidelines += f"[{i}] Halaman {page}\n"
            
            results["company_guidelines"] = company_guidelines
            print("✅ [Orchestrator] Company guidelines retrieved via RAG", file=sys.stderr)
            
        except Exception as e:
            error_msg = f"RAG Query error: {str(e)}"
            results["errors"].append(error_msg)
            print(f"❌ {error_msg}", file=sys.stderr)
    
    # ==================== PARALLEL EXECUTION ====================
    await asyncio.gather(
        fetch_android_studio_context(),
        fetch_postman_api(),
        fetch_kotlin_docs(),
        fetch_company_guidelines(),
        return_exceptions=True
    )
    
    # Format final output
    return json.dumps(results, indent=2, ensure_ascii=False)


@mcp.tool()
async def query_rag_directly(query: str) -> str:
    """
    Query RAG chain langsung untuk company documents.
    
    Args:
        query: Pertanyaan mengenai company documents
    
    Returns:
        Jawaban dari RAG chain dengan referensi sumber
    """
    if not RAG_AVAILABLE:
        return "❌ RAG Chain tidak tersedia"
    
    try:
        print(f"📚 [Orchestrator] Direct RAG Query: {query}", file=sys.stderr)
        
        response = rag_chain.invoke({"input": query})
        
        # Format output
        answer = response.get("answer", "No answer found")
        
        # Tambahkan sumber referensi
        if response.get("context"):
            answer += "\n\n📄 Sumber:\n"
            for i, doc in enumerate(response["context"], 1):
                page = doc.metadata.get("page", "?")
                answer += f"[{i}] Halaman {page}\n"
        
        return answer
        
    except Exception as e:
        return f"❌ RAG Query error: {str(e)}"


@mcp.tool()
async def query_specific_server(
    server_name: str,
    query: str
) -> str:
    """
    Query satu MCP server spesifik.
    
    Args:
        server_name: Pilih dari 'postman', 'android_studio', atau 'context7'
        query: Pertanyaan spesifik untuk server tersebut
    """
    valid_servers = list(MCP_SERVERS_CONFIG.keys()) + ["rag"]
    
    if server_name == "rag":
        return await query_rag_directly(query)
    
    if server_name not in MCP_SERVERS_CONFIG:
        return f"❌ Invalid server name. Choose from: {valid_servers}"
    
    try:
        print(f"🔍 [Orchestrator] Querying {server_name}...", file=sys.stderr)
        client = MultiServerMCPClient({server_name: MCP_SERVERS_CONFIG[server_name]})
        tools = await client.get_tools()
        agent = create_react_agent(orchestrator_llm, tools)
        
        response = await agent.ainvoke({
            "messages": [{"role": "user", "content": query}]
        })
        return response["messages"][-1].content
    except Exception as e:
        return f"❌ Error querying {server_name}: {str(e)}"


@mcp.tool()
async def health_check_all_servers() -> str:
    """
    Health check untuk MCP servers dan RAG availability.
    """
    results = {}

    # Define expected servers and their config requirements
    expected_servers = {
        "postman": ("POSTMAN_API_KEY", POSTMAN_API_KEY),
        "android_studio": ("ANDROID_PROJECT_ROOT", ANDROID_PROJECT_ROOT),
        "context7": (None, True)  # Context7 doesn't require env var
    }

    # ==================== CHECK MCP SERVERS ====================
    for server_name in expected_servers.keys():
        env_var, env_value = expected_servers[server_name]

        # Check if server is configured
        if server_name not in MCP_SERVERS_CONFIG:
            results[server_name] = {
                "status": "⚠️ NOT CONFIGURED",
                "reason": f"Environment variable {env_var} not set" if env_var else "Configuration missing",
                "env_var": env_var,
                "current_value": env_value[:20] + "..." if env_value and len(str(env_value)) > 20 else env_value
            }
            continue

        config = MCP_SERVERS_CONFIG[server_name]
        try:
            print(f"🏥 [Health Check] Testing {server_name}...", file=sys.stderr)
            client = MultiServerMCPClient({server_name: config})
            tools = await client.get_tools()
            results[server_name] = {
                "status": "✅ ONLINE",
                "tools_count": len(tools),
                "available_tools": [tool.name for tool in tools]
            }
        except Exception as e:
            import traceback
            error_detail = str(e)
            print(f"❌ [Health Check] {server_name} error: {error_detail}", file=sys.stderr)
            print(traceback.format_exc(), file=sys.stderr)
            results[server_name] = {
                "status": "❌ OFFLINE",
                "error": error_detail,
                "command": config.get("command"),
                "args": config.get("args")
            }

    # ==================== CHECK RAG ====================
    results["rag"] = {
        "status": "✅ AVAILABLE" if RAG_AVAILABLE else "❌ UNAVAILABLE",
        "direct_access": True,
        "notes": "Direct import from agent_pdf_rag.py (no MCP Server needed)",
        "diagnostic": RAG_ERROR_DETAIL if not RAG_AVAILABLE else None,
        "env_check": {
            "VECTOR_DATABASE_URL": "✅ Set" if os.getenv("VECTOR_DATABASE_URL") else "❌ Not set"
        }
    }

    return json.dumps(results, indent=2, ensure_ascii=False)


# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║   🎭 INTEGRATION ORCHESTRATOR - MCP Multi-Server Agent   ║
    ║                                                           ║
    ║   Architecture:                                           ║
    ║   • 3 MCP Servers (Postman, Android Studio, Context7)   ║
    ║   • Direct RAG Access (agent_pdf_rag.py - No MCP)       ║
    ║                                                           ║
    ║   Features:                                              ║
    ║   • get_complete_integration_context() → Aggregates all ║
    ║   • query_specific_server() → Query single source       ║
    ║   • query_rag_directly() → Direct RAG queries           ║
    ║   • health_check_all_servers() → System status          ║
    ╚═══════════════════════════════════════════════════════════╝
    """, file=sys.stderr)
    
    mcp.run(transport="stdio")