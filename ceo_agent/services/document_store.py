import shutil
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownTextSplitter

from base.retriever_base import RetrieverBase, RetrievalResult
from services.embedding_service import EmbeddingService


@dataclass
class ChunkConfig:
    chunk_size: int = 500
    chunk_overlap: int = 50
    separators: list[str] = field(
        default_factory=lambda: ["\n\n", "\n", ". ", " ", ""]
    )
    is_markdown: bool = True  # Set to True to handle your corporate .md files cleanly


@dataclass
class ChromaConfig:
    persist_directory: str = "./chroma_company_db"
    collection_name: str = "company_knowledge"


class DocumentStore(RetrieverBase):
    def __init__(
            self,
            embedding_service: EmbeddingService,
            chroma_config: ChromaConfig = ChromaConfig(),
            chunk_config: ChunkConfig = ChunkConfig(),
            cleanup_on_exit: bool = False,
    ) -> None:
        if not chroma_config.collection_name:
            raise ValueError("ChromaConfig.collection_name is required and cannot be empty.")

        self._embedder = embedding_service
        self._chroma_cfg = chroma_config
        self._cleanup_on_exit = cleanup_on_exit

        # Select the optimal splitter based on your file type requirement
        if chunk_config.is_markdown:
            self._splitter = MarkdownTextSplitter(
                chunk_size=chunk_config.chunk_size,
                chunk_overlap=chunk_config.chunk_overlap
            )
        else:
            self._splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_config.chunk_size,
                chunk_overlap=chunk_config.chunk_overlap,
                separators=chunk_config.separators,
            )

        # Initialize Chroma DB locally using your existing Google embedding model wrapper
        self._store = Chroma(
            collection_name=chroma_config.collection_name,
            embedding_function=self._embedder.get_model(),
            persist_directory=chroma_config.persist_directory,
            collection_metadata={"hnsw:space": "cosine"}
        )

    def load_file(self, path: str, metadata: dict | None = None) -> list[Document]:
        """Reads a file (.md or .txt) and chunks it while keeping historical metadata structure."""
        text = Path(path).read_text(encoding="utf-8")
        base_meta = {"source": Path(path).name, **(metadata or {})}

        chunks = self._splitter.create_documents([text], metadatas=[base_meta])
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
        return chunks

    def index(self, documents: list[Document]) -> None:
        """Saves the chunks natively into your local Chroma database."""
        self._store.add_documents(documents=documents)

    def index_markdown_directory(self, docs_directory: str) -> None:
        """Reads all .md files in a directory and indexes them into Chroma DB."""
        dir_path = Path(docs_directory)
        if not dir_path.exists():
            print(f"Directory {docs_directory} not found.")
            return

        for md_file in dir_path.glob("*.md"):
            try:
                # Use our load_file method to handle markdown partitioning cleanly
                chunks = self.load_file(str(md_file))
                self.index(chunks)
                print(f"Successfully processed and indexed: {md_file.name}")
            except Exception as e:
                print(f"Error reading and indexing {md_file.name}: {e}")

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        """Performs a standard cosine similarity search and matches your score thresholds."""
        raw = self._store.similarity_search_with_score(query, k=top_k)
        return [RetrievalResult(document=doc, score=score) for doc, score in raw]

    def retrieve_mmr(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        """Performs Max Marginal Relevance (MMR) search natively in Chroma DB."""
        docs = self._store.max_marginal_relevance_search(
            query, k=top_k, fetch_k=top_k * 4
        )
        return [RetrievalResult(document=doc, score=1.0) for doc in docs]

    def clear(self) -> None:
        """Cleans all vectors and texts inside the active collection."""
        all_ids = self._store.get()["ids"]
        if all_ids:
            self._store.delete(ids=all_ids)

    def __enter__(self) -> "DocumentStore":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._cleanup_on_exit:
            self.clear()
            # Deletes the hard disk folder directory cleanly upon programmatic close
            if Path(self._chroma_cfg.persist_directory).exists():
                shutil.rmtree(self._chroma_cfg.persist_directory)
            print("clean up done")