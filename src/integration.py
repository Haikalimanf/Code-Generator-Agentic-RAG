"""
Example: Integrasi GitLab Agent dengan Integration Orchestrator

Workflow:
1. GitLab Agent fetch requirement dari issue
2. Pass ke Orchestrator untuk mendapatkan technical context
3. Orchestrator return aggregated data untuk code generation

FIX: Menggunakan pattern yang sesuai dengan langchain-mcp-adapters 0.1.0+
     Tools harus di-invoke melalui ReAct Agent, bukan direct call_tool()
"""

import asyncio
import json
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
import os
import sys
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY", "")
BASE_URL = "https://openrouter.ai/api/v1"
MODEL_NAME = os.getenv("MODEL_NAME", "anthropic/claude-sonnet-4.5")

ORCHESTRATOR_PATH = r"D:\RAG\Membuat MCP Server\src\orchestrator.py"

# ==================== HELPER: Create Orchestrator LLM ====================
def get_orchestrator_llm():
    """Create LLM untuk orchestrator queries"""
    return ChatOpenAI(
        model=MODEL_NAME,
        temperature=0.0,
        api_key=API_KEY,
        base_url=BASE_URL,
        max_tokens=2048,
    )


# ==================== CONTOH 1: Simple Usage ====================
async def example_basic_usage():
    """Contoh paling sederhana - ambil semua context"""
    
    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }
    
    print("[1] Connecting to Orchestrator...")
    client = MultiServerMCPClient(orchestrator_config)
    
    try:
        # Get all available tools
        tools = await client.get_tools()
        print(f"✅ Connected! Found {len(tools)} tools:\n")
        
        for tool in tools:
            print(f"  • {tool.name}")
            print(f"    {tool.description}\n")
        
        # Create agent to use the tools
        print("[2] Creating agent to query orchestrator...")
        llm = get_orchestrator_llm()
        # ✅ FIXED: Updated import
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
        )
        
        print("[3] Querying orchestrator for context...")
        response = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": "Get integration context for: Implement user login with JWT authentication. Include API contracts but not Kotlin docs."
            }]
        })
        
        print("\n✅ Response received:")
        last_msg = response["messages"][-1]
        print(f"\n{last_msg.content if hasattr(last_msg, 'content') else last_msg}\n")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


# ==================== CONTOH 2: Integration dengan GitLab Agent ====================
async def example_gitlab_integration():
    """Simulasi flow lengkap: GitLab → Orchestrator → Code Generator"""
    
    print("\n" + "=" * 70)
    print("📋 WORKFLOW: GitLab Issue → Requirement → Orchestrator Context")
    print("=" * 70)
    
    # Step 1: Ambil requirement dari GitLab
    print("\n[Step 1/3] 📥 Mengambil requirement dari GitLab...")
    
    try:
        from agent_gitlab import run_gitlab_analyst_agent
        
        project_id = "81209841"
        issue_iid = 1
        
        print(f"  Connecting to GitLab (project: {project_id}, issue: {issue_iid})...")
        requirement = run_gitlab_analyst_agent(project_id, issue_iid)
        
        print(f"  ✅ Requirement extracted ({len(requirement)} chars)")
        print("\n  📝 Preview:")
        preview = requirement[:400].replace('\n', '\n  ') + ("..." if len(requirement) > 400 else "")
        print(f"  {preview}\n")
        
    except Exception as e:
        print(f"  ⚠️  GitLab connection failed: {e}")
        print("  Using simulated requirement instead...\n")
        
        requirement = """
Feature: Implement dark mode toggle

As a user, I want to switch between light and dark themes.

Acceptance Criteria:
- Add toggle button in Settings screen
- Use Material3 color schemes
- Persist preference using DataStore
- API integration for user preferences
        """
    
    # Step 2: Determine what context is needed
    print("[Step 2/3] 🔍 Analyzing requirement...")
    needs_api = "api" in requirement.lower() or "endpoint" in requirement.lower()
    needs_kotlin_docs = "material3" in requirement.lower() or "compose" in requirement.lower()
    
    print(f"  API Contracts needed: {'✅ Yes' if needs_api else '❌ No'}")
    print(f"  Kotlin Updates needed: {'✅ Yes' if needs_kotlin_docs else '❌ No'}\n")
    
    # Step 3: Query Orchestrator
    print("[Step 3/3] 🎯 Querying Orchestrator for technical context...")
    
    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }
    
    print("  Connecting to orchestrator MCP server...")
    client = MultiServerMCPClient(orchestrator_config)
    
    try:
        # Get available tools dari orchestrator
        tools = await client.get_tools()
        print(f"  ✅ Available tools: {len(tools)}\n")
        
        # Create agent dengan orchestrator tools
        llm = get_orchestrator_llm()
        # ✅ FIXED: Updated import
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
        )
        
        # Build query for agent
        query = f"""
Analyze this requirement and fetch the complete integration context:

{requirement}

Use the get_complete_integration_context tool with:
- include_api: {str(needs_api).lower()}
- include_kotlin_docs: {str(needs_kotlin_docs).lower()}

Provide a structured summary of what you found.
"""
        
        print("  Invoking orchestrator agent...")
        response = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": query
            }]
        })
        
        # Extract final response
        last_msg = response["messages"][-1]
        final_answer = last_msg.content if hasattr(last_msg, 'content') else str(last_msg)
        
        print("\n" + "=" * 70)
        print("✅ ORCHESTRATOR RESPONSE:")
        print("=" * 70)
        print(final_answer)
        print("=" * 70 + "\n")
        
        return {
            "requirement": requirement,
            "context": final_answer,
            "needs_api": needs_api,
            "needs_kotlin": needs_kotlin_docs
        }
        
    except Exception as e:
        print(f"\n  ❌ Orchestrator error: {e}")
        print(f"     Make sure Terminal 1 is running: uv run src/orchestrator.py")
        import traceback
        traceback.print_exc()
        return None


# ==================== CONTOH 3: Health Check ====================
async def example_health_check():
    """Cek semua MCP servers sebelum processing"""
    
    print("\n" + "=" * 70)
    print("🏥 MCP SERVERS HEALTH CHECK")
    print("=" * 70 + "\n")
    
    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }
    
    client = MultiServerMCPClient(orchestrator_config)
    
    try:
        tools = await client.get_tools()
        
        # Use health_check tool through agent
        llm = get_orchestrator_llm()
        # ✅ FIXED: Updated import
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
        )
        
        response = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": "Check health status of all MCP servers and report which ones are online."
            }]
        })
        
        last_msg = response["messages"][-1]
        print(last_msg.content if hasattr(last_msg, 'content') else last_msg)
        
    except Exception as e:
        print(f"❌ Health check error: {e}")


# ==================== CONTOH 4: Query Specific Server ====================
async def example_targeted_query():
    """Query satu server tertentu"""
    
    print("\n" + "=" * 70)
    print("📚 TARGETED MCP SERVER QUERY")
    print("=" * 70 + "\n")
    
    orchestrator_config = {
        "orchestrator": {
            "command": sys.executable,
            "args": [ORCHESTRATOR_PATH],
            "transport": "stdio",
            "env": {**os.environ},
        }
    }
    
    client = MultiServerMCPClient(orchestrator_config)
    
    try:
        tools = await client.get_tools()
        
        llm = get_orchestrator_llm()
        # ✅ FIXED: Updated import
        from langgraph.prebuilt import create_react_agent
        agent = create_react_agent(
            model=llm,
            tools=tools,
        )
        
        response = await agent.ainvoke({
            "messages": [{
                "role": "user",
                "content": """Query the rag server directly:
'Berikan best practices untuk Android development'

Use the query_specific_server tool with server_name='rag'."""
            }]
        })
        
        last_msg = response["messages"][-1]
        print(last_msg.content if hasattr(last_msg, 'content') else last_msg)
        
    except Exception as e:
        print(f"❌ Query error: {e}")


# ==================== ENTRY POINT ====================
if __name__ == "__main__":
    print("""
+======================================================================+
|                                                                      |
|    GitLab -> Orchestrator Integration Examples                       |
|                                                                      |
|    Prerequisites:                                                    |
|    * Terminal 1: uv run src/orchestrator.py (RUNNING NOW)            |
|    * Terminal 2: This script                                         |
|                                                                      |
|    Choose an example to run (uncomment in __main__)                  |
|                                                                      |
+======================================================================+
""")
    
    print("\nAvailable examples:")
    print("  1. example_basic_usage() - Simple tool discovery")
    print("  2. example_gitlab_integration() - Full GitLab → Orchestrator (RECOMMENDED)")
    print("  3. example_health_check() - Check server status")
    print("  4. example_targeted_query() - Query RAG directly")
    
    print("\n🎯 Running: example_gitlab_integration()\n")
    
    # Run examples (uncomment as needed):
    # asyncio.run(example_basic_usage())
    asyncio.run(example_gitlab_integration())
    # asyncio.run(example_health_check())
    # asyncio.run(example_targeted_query())