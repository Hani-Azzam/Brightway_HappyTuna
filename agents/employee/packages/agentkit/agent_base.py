from abc import ABC, abstractmethod


class AgentBase(ABC):
    """Common interface for every agent.

    Standardizing on `chat()` + `reset()` lets coordinators, dispatchers, and the
    evaluation harness drive any agent without knowing its internals. The optional
    `history` carries working memory (recent turns) into a single reasoning cycle.
    """

    @abstractmethod
    def chat(self, user_input: str, history: list[dict] | None = None) -> str: ...

    @abstractmethod
    def reset(self) -> None: ...

    def __enter__(self) -> "AgentBase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.reset()
