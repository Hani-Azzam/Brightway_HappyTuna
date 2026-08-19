import math
from dataclasses import dataclass

from langchain_google_genai import GoogleGenerativeAIEmbeddings


@dataclass
class EmbeddingConfig:
    api_key: str
    model_name: str = "models/text-embedding-004" #defulat model


class EmbeddingService:
    def __init__(self, config: EmbeddingConfig) -> None:
        self._model = GoogleGenerativeAIEmbeddings(
            model=config.model_name,
            google_api_key=config.api_key,
        )

    def embed(self, text: str) -> list[float]:
        return self._model.embed_query(text)

    def similarity(self, a: list[float], b: list[float]) -> float: #no need to understand this function
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x ** 2 for x in a))
        mag_b = math.sqrt(sum(x ** 2 for x in b))
        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0
        return dot / (mag_a * mag_b)

    def get_model(self) -> GoogleGenerativeAIEmbeddings:
        return self._model
