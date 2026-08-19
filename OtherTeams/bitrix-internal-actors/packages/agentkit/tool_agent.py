"""ReAct agent: Plan -> Act -> Observe -> repeat.

This is the reasoning core reused by every simulated actor (Employee, COO, ...).
It is provider-agnostic: it takes any object satisfying the `LLM` protocol and
speaks plain OpenAI-style message dicts, so there is no LangChain / provider
dependency here.

Ported from the workspace `07_multi_agents`, with two deliberate changes:
  - messages are plain dicts instead of langchain message objects;
  - `system_hint` (used to inject a persona/system prompt) and an optional
    `history` (working memory) are supported.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from packages.agentkit.agent_base import AgentBase
from packages.agentkit.llm import LLM
from packages.agentkit.tool_executor import ToolExecutor


@dataclass
class ReActConfig:
    max_steps: int = 6       # hard cap on Plan/Act/Observe iterations
    max_answer_length: int = 600
    system_hint: str = ""         # persona / domain rules injected into the system prompt


def _parse_json(text: str) -> dict | None:
    """
    Extract a JSON object from the LLM's raw response.
    Handles the common case where the LLM wraps JSON in markdown code fences
    even when explicitly told not to — a known LLM behavior.
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip().strip("`").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return None


def _build_system_prompt(tool_schemas: list[dict], system_hint: str = "") -> str:
    tools_section = ""
    for s in tool_schemas:
        props = s["parameters"].get("properties", {})
        required = s["parameters"].get("required", [])
        args_lines = ""
        for pname, pdef in props.items():
            req = " (required)" if pname in required else " (optional)"
            enum_hint = (
                f" — one of: {', '.join(str(v) for v in pdef['enum'])}"
                if "enum" in pdef else ""
            )
            args_lines += (
                f"\n    {pname} ({pdef['type']}{req}){enum_hint}: {pdef.get('description', '')}"
            )
        tools_section += (
            f"\nTool: {s['name']}\nDescription: {s['description']}\nArguments:{args_lines}\n"
        )

    hint_section = f"\n\n{system_hint}\n" if system_hint else ""
    return f"""You are a helpful assistant with access to tools.{hint_section}
RESPONSE FORMAT — follow exactly:
- To call a tool, output ONLY this JSON (one object, no surrounding text):
  {{"action": "tool_name", "args": {{"arg_name": "value"}}}}
- To give a final answer, output ONLY this JSON:
  {{"action": "final_answer", "answer": "your answer here"}}

RULES:
1. Output ONE JSON object per response — no prose, no markdown, no code fences.
2. Use a tool when you need to compute a value or look up / send information.
3. After receiving a tool result, decide: call another tool or give the final_answer.
4. If a tool returns an error, include it clearly in the final_answer.
5. Never invent a tool name — use only the tools listed below.

Available tools:{tools_section}"""


class ToolAgent(AgentBase):
    def __init__(
        self,
        llm_client: LLM,
        executor: ToolExecutor,
        config: ReActConfig | None = None,
    ) -> None:
        self._llm = llm_client
        self._executor = executor
        self._config = config or ReActConfig()

    def chat(self, user_input: str, history: list[dict] | None = None) -> str:
        self._executor.clear_traces()
        messages: list[dict] = [
            {"role": "system", "content": _build_system_prompt(
                self._executor.tool_schemas(), self._config.system_hint)}
        ]
        for turn in history or []:
            role = "user" if turn.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": turn["content"]})
        messages.append({"role": "user", "content": user_input})

        for step in range(1, self._config.max_steps + 1):
            self._executor.log_trace(step, "PLAN", None, "LLM deciding next action...")
            raw = self._llm.invoke(messages)
            self._executor.log_trace(step, "PLAN", None, f"LLM output → {raw[:150]}")
            messages.append({"role": "assistant", "content": raw})

            parsed = _parse_json(raw)
            if parsed is None:
                messages.append({
                    "role": "user",
                    "content": "Invalid format. Respond with ONLY a single JSON object — "
                               "no prose, no markdown.",
                })
                repair = self._llm.invoke(messages)
                messages.append({"role": "assistant", "content": repair})
                parsed = _parse_json(repair)
                if parsed is None:
                    return "I had trouble producing a valid response format. Please try rephrasing your question."

            action = parsed.get("action", "")
            if action == "final_answer":
                answer = str(parsed.get("answer", ""))
                if len(answer) > self._config.max_answer_length:
                    answer = answer[:self._config.max_answer_length] + " [truncated]"
                self._executor.log_trace(step, "OBSERVE", None, f"FINAL: {answer[:120]}")
                return answer

            result = self._executor.execute(step, action, parsed.get("args", {}))
            observation = (
                f"Tool '{action}' returned: {result.value}"
                if result.ok
                else f"Tool '{action}' failed: {result.error}. Report this error in your final_answer."
            )
            self._executor.log_trace(step, "OBSERVE", None, observation[:120])
            messages.append({"role": "user", "content": observation})

        return "Reached the maximum step limit without a final answer. Please try a simpler question."

    def reset(self) -> None:
        self._executor.clear_traces()
