import logging
from typing import Optional, TypeVar, Type
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel

from src.config.settings import settings

logger = logging.getLogger("llm_factory")

T = TypeVar("T", bound=BaseModel)


def create_llm(temperature: float = 0.0, max_tokens: Optional[int] = None) -> ChatOpenAI:
    kwargs = {
        "model": settings.model_name,
        "api_key": settings.openrouter_api_key,
        "base_url": settings.openrouter_base_url,
        "temperature": temperature,
    }
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    return ChatOpenAI(**kwargs)


def create_agent_with_memory(
    llm: ChatOpenAI,
    tools: list[BaseTool],
    system_prompt: str,
    agent_name: str,
    thread_id: str = "default",
):
    from langchain.agents import create_agent

    memory = MemorySaver()
    agent = create_agent(
        llm,
        tools,
        system_prompt=system_prompt,
        name=agent_name,
        checkpointer=memory,
    )
    return agent, {"configurable": {"thread_id": thread_id}}


def execute_agent_and_structure(
    agent_executor,
    agent_config: dict,
    user_input: str,
    llm: ChatOpenAI,
    output_schema: Type[T],
    agent_label: str = "Agent",
) -> T:
    logger.info("[%s] Starting analysis: %s", agent_label, user_input[:80])

    final_output = ""
    for chunk in agent_executor.stream(
        {"messages": [("human", user_input)]},
        agent_config,
        stream_mode="updates",
    ):
        for node_name, node_update in chunk.items():
            logger.info("[%s] Node: %s processing...", agent_label, node_name)
            if "messages" in node_update:
                last_msg = node_update["messages"][-1]
                if hasattr(last_msg, "content") and last_msg.content:
                    final_output = last_msg.content

    logger.info("[%s] Analysis complete. Structuring output...", agent_label)

    llm_structured = llm.with_structured_output(output_schema)
    result = llm_structured.invoke(final_output)
    if not isinstance(result, output_schema):
        raise TypeError(
            f"[{agent_label}] Expected {output_schema.__name__}, got {type(result).__name__}"
        )
    return result

def load_stage_prompt(stage_name: str) -> str:
    """
    Membaca instruksi kognitif (Layer 2) dari folder direktori ICM workspace.
    """
    # Menargetkan file CONTEXT.md di dalam folder stage yang aktif
    prompt_path = Path("workspace") / "stages" / stage_name / "CONTEXT.md"
    if not prompt_path.exists():
        prompt_path = Path("workspace") / "stages" / stage_name / "CONTEXT.MD"
    
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt kognitif untuk {stage_name} tidak ditemukan di {prompt_path}")
        
    with open(prompt_path, "r", encoding="utf-8") as file:
        return file.read()