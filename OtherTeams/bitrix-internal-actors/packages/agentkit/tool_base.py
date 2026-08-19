"""Tool abstraction shared by every agent.

A tool is the only way an agent affects the world: the ReAct loop chooses a tool
by name, the executor validates + runs it, and the result is fed back as an
observation. Ported from the workspace `07_multi_agents` tutorial, with no
framework dependency so any service can reuse it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSchema:
    name: str          # machine-readable identifier the LLM writes in its JSON output
    description: str   # plain English — what the LLM reads to decide WHEN to call the tool
    parameters: dict   # JSON Schema object describing every argument


@dataclass
class ToolResult:
    value: Any = None
    error: str | None = None
    is_idempotent: bool = True  # True = safe to retry; False = side effects, run exactly once

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolBase(ABC):
    @property
    @abstractmethod
    def schema(self) -> ToolSchema: ...

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult: ...
