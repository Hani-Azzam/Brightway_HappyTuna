import os
from dataclasses import dataclass
from base.tool_agent import ToolAgent, ReActConfig
from services.llm_client import LlmClient, LlmConfig
from services.tool_executor import ToolExecutor
from services.embedding_service import EmbeddingService, EmbeddingConfig
from services.document_store import DocumentStore, ChromaConfig
from services.rag_pipeline import RagPipeline, RagConfig

from tools.publish_article import PublishArticleTool
from tools.search_news import SearchNewsTool
from tools.search_knowledge import SearchKnowledgeTool
from tools.post_social import PostSocialTool
from prompts import JOURNALIST_SYSTEM_HINT, JOURNALIST_DESCRIPTION


@dataclass
class JournalistConfig:
    """
    All configuration for the Journalist agent.
    Loaded from environment variables with sensible defaults.
    """
    # Two providers on purpose, on the stable-release branch: the reasoning model
    # is Claude Haiku like every other agent, but Anthropic has no embeddings
    # API, so the RAG knowledge base still embeds through Gemini.
    anthropic_api_key: str
    gemini_api_key: str
    embedding_model: str = "models/gemini-embedding-001"
    # Embedded Chroma (langchain_chroma persist_directory) — no separate server.
    chroma_persist_dir: str = "/data/chroma"
    model_name: str = "claude-haiku-4-5"
    temperature: float = 0.2      # low = more factual, less creative
    max_steps: int = 12
    max_answer_length: int = 800
    rag_top_k: int = 4
    rag_refuse_threshold: float = 0.30

    @classmethod
    def from_env(cls) -> "JournalistConfig":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"),
            chroma_persist_dir=os.getenv("CHROMA_PERSIST_DIR", "/data/chroma"),
            model_name=os.getenv("JOURNALIST_MODEL", "claude-haiku-4-5"),
            temperature=float(os.getenv("JOURNALIST_TEMPERATURE", "0.2")),
            max_steps=int(os.getenv("JOURNALIST_MAX_STEPS", "12")),
        )


class JournalistAgent(ToolAgent):
    """
    The Journalist agent for the BitriX HappyTuna crisis simulation.

    Personality: neutral, fact-focused, credibility-driven.
    Framework: LangChain (via ToolAgent + ReAct loop)
    Memory: Chroma DB (food safety knowledge base)
    Tools: publish_article, search_news, search_knowledge, post_social

    Usage:
        config = JournalistConfig.from_env()
        with JournalistAgent(config) as agent:
            response = agent.chat("salmonella detected at HappyTuna Line A")
            print(response)
    """

    role = "journalist"
    description = JOURNALIST_DESCRIPTION

    def __init__(self, config: JournalistConfig) -> None:
        # --- LLM ---
        llm_client = LlmClient(LlmConfig(
            api_key=config.anthropic_api_key,
            model_name=config.model_name,
            temperature=config.temperature,
        ))

        # --- Embedding service (for Chroma RAG) ---
        embedding_service = EmbeddingService(EmbeddingConfig(
            api_key=config.gemini_api_key,
            model_name=config.embedding_model,  

        ))

        # --- Document store (Chroma DB - journalist collection) ---
        document_store = DocumentStore(
            embedding_service=embedding_service,
            chroma_config=ChromaConfig(
                collection_name="journalist",
                persist_directory=config.chroma_persist_dir,
            ),
        )

        # --- RAG pipeline ---
        rag_pipeline = RagPipeline(
            llm_client=llm_client,
            document_store=document_store,
            config=RagConfig(
                top_k=config.rag_top_k,
                refuse_threshold=config.rag_refuse_threshold,
                use_mmr=False,
            ),
        )

        # --- Tool executor ---
        executor = ToolExecutor(max_retries=2, base_delay=0.5)

        # --- Register all tools ---
        executor.register(SearchKnowledgeTool(document_store=document_store))
        executor.register(SearchNewsTool())
        executor.register(PublishArticleTool())
        executor.register(PostSocialTool())

        # --- ReAct config ---
        react_config = ReActConfig(
            max_steps=config.max_steps,
            max_answer_length=config.max_answer_length,
            system_hint=JOURNALIST_SYSTEM_HINT,
            # A press cycle that ends without an article produced nothing at all,
            # so the loop pushes back once instead of accepting `final_answer`.
            required_action="publish_article",
        )

        # --- Init parent ToolAgent ---
        super().__init__(
            llm_client=llm_client,
            executor=executor,
            config=react_config,
        )

        # Store for later use (e.g. indexing new documents)
        self._document_store = document_store
        self._rag_pipeline = rag_pipeline
        # NOTE: deliberately NOT `self._config = config`. That line used to sit
        # here and clobbered the ReActConfig that super().__init__ just stored,
        # which is what the ReAct loop reads. It looked harmless because
        # JournalistConfig happens to carry max_steps and max_answer_length too
        # -- but system_hint is not among them, so the journalist's persona and
        # publishing rules were silently dropped and the loop ran on the base
        # "You are a helpful assistant" prompt. Nothing ever read the value back,
        # so the assignment bought nothing. Journalist settings live in `config`,
        # which the constructor already uses directly.
        self._journalist_config = config

    def index_knowledge(self, directory: str) -> None:
        """
        Load background documents from a directory into Chroma DB.
        Call this once at startup before running the agent.

        Args:
            directory: path to folder containing .txt knowledge files
                       e.g. "agents/journalist/knowledge/"
        """
        from pathlib import Path
        docs = []
        path = Path(directory)
        if not path.exists():
            print(f"[Journalist] Knowledge directory not found: {directory}")
            return

        for file in path.rglob("*.txt"):
            chunks = self._document_store.load_file(str(file))
            docs.extend(chunks)
            print(f"[Journalist] Loaded: {file.name} → {len(chunks)} chunks")

        if docs:
            self._document_store.index(docs)
            print(f"[Journalist] Indexed {len(docs)} chunks into Chroma DB")
        else:
            print(f"[Journalist] No .txt files found in {directory}")

    def quick_answer(self, question: str) -> str:
        """
        Query the RAG pipeline directly without the full ReAct loop.
        Useful for background research queries that don't need tool use.
        """
        return self._rag_pipeline.answer(question)

    def reset(self) -> None:
        """Clears the tool executor traces between runs."""
        super().reset()