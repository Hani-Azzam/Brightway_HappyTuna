from dataclasses import dataclass
from langchain_core.messages import HumanMessage, SystemMessage
from base.retriever_base import RetrievalResult
from services.document_store import DocumentStore
from services.llm_client import LlmClient


@dataclass
class RagConfig:
    top_k: int = 4
    refuse_threshold: float = 0.30 # should check the embedder system what is the best threshould its different from model to another model (gimine or another one )
    use_mmr: bool = False


class RagPipeline:
    def __init__(self, llm_client: LlmClient, document_store: DocumentStore, config: RagConfig = RagConfig()):
        self._llm = llm_client
        self._store = document_store
        self.config = config

    def answer(self, question: str) -> str:
        text, _ = self.answer_with_sources(question)
        return text

    def _should_refuse(self, results: list[RetrievalResult]) -> bool:
        if not results:
            return True
        if self.config.use_mmr:
            return False
        return max(r.score for r in results) < self.config.refuse_threshold

    def answer_with_sources(self, question: str) -> tuple[str, list[RetrievalResult]]:
        results = (
            self._store.retrieve_mmr(question, self.config.top_k)
            if self.config.use_mmr
            else self._store.retrieve(question, self.config.top_k)
        )

        if self._should_refuse(results):
            return (
                "I don't have reliable information on that topic in my knowledge base.",
                [],
            )

        context = "\n\n".join(
            f"[{r.document.metadata.get('source', '?')}]\n{r.document.page_content}"
            for r in results
        )
        messages = [
            SystemMessage(
                content=(
                    "Answer using ONLY the provided context. "
                    "Cite the source filename at the end of your answer"
                )
            ),
            HumanMessage(content=f"Context:\n{context}\n\nQuestion: {question}"),
        ]
        return self._llm.invoke(messages), results
