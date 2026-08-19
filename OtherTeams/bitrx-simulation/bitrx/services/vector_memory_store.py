from base.memory_base import MemoryBase, MemoryEntry
from services.embedding_service import EmbeddingService

class VectorMemoryStore(MemoryBase):
    def __init__(self, embedding_service: EmbeddingService) -> None:
        self._embedder = embedding_service
        self._entries : list[MemoryEntry] = []

    def add(self, role: str, content: str) -> None:
        vec = self._embedder.embed(content)
        self._entries.append(MemoryEntry(role=role, content=content, embedding=vec))

    def search(self, query: str, top_k: int = 3) -> list[MemoryEntry]:
        if not self._entries:
            return []
        query_vec = self._embedder.embed(query)
        ranked = sorted(
            self._entries,
            key=lambda e: self._embedder.similarity(query_vec, e.embedding),
            reverse=True,
        )
        return ranked[:top_k]

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)