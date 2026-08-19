"""agentkit — the shared agent framework for the BitriX simulated actors.

Provider-agnostic reasoning core (ReAct loop + tools + registry). The concrete
LLM client lives in `packages/llm`; agentkit depends only on the `LLM` protocol.
"""
from packages.agentkit.agent_base import AgentBase
from packages.agentkit.llm import LLM
from packages.agentkit.registry import Registry
from packages.agentkit.tool_agent import ReActConfig, ToolAgent
from packages.agentkit.tool_base import ToolBase, ToolResult, ToolSchema
from packages.agentkit.tool_executor import StepTrace, ToolExecutor

__all__ = [
    "AgentBase",
    "LLM",
    "Registry",
    "ReActConfig",
    "ToolAgent",
    "ToolBase",
    "ToolResult",
    "ToolSchema",
    "StepTrace",
    "ToolExecutor",
]
