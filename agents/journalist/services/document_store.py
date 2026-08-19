from dataclasses import dataclass, field
from pathlib import Path
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from base.retriever_base import RetrieverBase, RetrievalResult
from services.embedding_service import EmbeddingService

'''
Chroma runs inside your Docker network alongside your other services — 
no internet, no API key, no cost, no latency.
'''
@dataclass
class ChunkConfig:
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: list[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", " ", ""]
    )


@dataclass
class ChromaConfig:
    collection_name: str        # e.g. "journalist" or "regulator"
    persist_directory: str      # e.g. "/data/chroma"


class DocumentStore(RetrieverBase):
    def __init__(
            self,
            embedding_service: EmbeddingService,
            chroma_config: ChromaConfig,
            chunk_config: ChunkConfig = ChunkConfig(),
            cleanup_on_exit: bool = False,
    ) -> None:
        self._embedder = embedding_service
        self._cfg = chroma_config
        self._cleanup_on_exit = cleanup_on_exit
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_config.chunk_size,
            chunk_overlap=chunk_config.chunk_overlap,
            separators=chunk_config.separators,
        )
        self._store = Chroma(
            collection_name=chroma_config.collection_name,
            embedding_function=embedding_service.get_model(),
            persist_directory=chroma_config.persist_directory,
        )

    def load_file(self, path: str, metadata: dict | None = None) -> list[Document]:
        text = Path(path).read_text(encoding="utf-8")
        base_meta = {"source": Path(path).name, **(metadata or {})}
        chunks = self._splitter.create_documents([text], metadatas=[base_meta])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
        return chunks

    def index(self, documents: list[Document]) -> None:
        self._store.add_documents(documents)

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        print(f"[DEBUG] query={query!r} top_k={top_k!r} type={type(top_k)}")
        try:
            raw = self._store.similarity_search_with_relevance_scores(query, k=int(top_k))
            return [RetrievalResult(document=doc, score=float(score)) for doc, score in raw]
        except Exception as e:
            print(f"[DocumentStore] retrieve error: {e}")
            import traceback
            traceback.print_exc()  # ← add this to see the full stack trace
            try:
                docs = self._store.similarity_search(query, k=int(top_k))
                return [RetrievalResult(document=doc, score=1.0) for doc in docs]
            except Exception as e2:
                print(f"[DocumentStore] fallback failed: {e2}")
                traceback.print_exc()  # ← and this
                return []

            
    def retrieve_mmr(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        docs = self._store.max_marginal_relevance_search(query, k=top_k)
        return [RetrievalResult(document=doc, score=1.0) for doc in docs]

    def clear(self) -> None:
        self._store.delete_collection()

    def __enter__(self) -> "DocumentStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._cleanup_on_exit:
            self.clear()