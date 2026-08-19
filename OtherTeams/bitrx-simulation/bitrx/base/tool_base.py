from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolSchema:
    name: str         # machine-readable identifier the LLM writes in its JSON output -> no spaces, lowercase
    description: str  # plain English -> this is what the LLM reads to decide WHEN to call the tool
    parameters: dict  # JSON Schema object -> it defines every argument with its type and a short description

@dataclass
class ToolResult:
    value: Any = None
    error: str | None = None
    is_idempotent: bool = True

    @property
    def ok(self) -> bool:
        return self.error is None


class ToolBase(ABC):

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        ...

    @abstractmethod
    def run(self, **kwargs) -> ToolResult:
        ...