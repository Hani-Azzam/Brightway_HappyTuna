"""EmployeeAgent — a persona wrapped around the shared ReAct engine.

The engine (`agentkit.ToolAgent`) is unchanged; the persona supplies the system
prompt (via `system_hint`), the step budget, and the stable `employee_id` the
registry keys on.
"""
from __future__ import annotations

from packages.agentkit.llm import LLM
from packages.agentkit.tool_agent import ReActConfig, ToolAgent
from packages.agentkit.tool_executor import ToolExecutor

from services.employee.personas.persona import Persona


class EmployeeAgent(ToolAgent):
    def __init__(self, llm: LLM, executor: ToolExecutor, persona: Persona) -> None:
        super().__init__(
            llm,
            executor,
            ReActConfig(
                max_steps=persona.max_steps,
                system_hint=persona.render_system_prompt(),
            ),
        )
        self.employee_id = persona.employee_id   # registry key
        self.persona = persona
