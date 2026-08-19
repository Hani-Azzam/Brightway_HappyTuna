from abc import ABC, abstractmethod

class AgentBase(ABC):

    @abstractmethod
    def chat(self, user_input: str) -> str:
        ...

    @abstractmethod
    def reset(self) -> None:
        pass

    ## this two function are used in with
    def __enter__(self)  -> 'AgentBase':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.reset()