from dataclasses import dataclass
from langchain_google_genai import GoogleGenerativeAIEmbeddings


@dataclass
class EmbeddingConfig:
    api_key: str
    model_name: str = "models/text-embedding-004"  # Default Google v4 model


class EmbeddingService:
    def __init__(self, config: EmbeddingConfig) -> None:
        # Initialize the native LangChain Google Embeddings model
        self._model = GoogleGenerativeAIEmbeddings(
            model=config.model_name,
            google_api_key=config.api_key
        )

    def get_model(self) -> GoogleGenerativeAIEmbeddings:
        """Returns the underlying model object required directly by Chroma DB."""
        return self._model