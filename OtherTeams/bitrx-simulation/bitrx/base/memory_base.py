from abc import ABC, abstractmethod
from dataclasses import  dataclass, field



@dataclass
class MemoryEntry:
    role: str
    content: str
    embedding: list[float] = field(default_factory=list)


class MemoryBase(ABC):

    @abstractmethod
    def add(self, role: str, content: str) -> None:
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 3) -> list[MemoryEntry]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass
