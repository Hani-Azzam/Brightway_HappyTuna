from dataclasses import dataclass

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


@dataclass
class LlmConfig:
    api_key: str
    model_name: str = "claude-haiku-4-5"
    temperature: float = 0.0
    # Anthropic requires an explicit output cap and LangChain's default is 1024,
    # which is enough to truncate a multi-step plan mid-JSON. Gemini, which this
    # client used before, had no comparably tight default.
    max_tokens: int = 4096


class LlmClient:
    def __init__(self, config: LlmConfig):
        if not config.api_key:
            raise ValueError("LlmConfig.api_key is required and cannot be empty.")
        if not config.model_name:
            raise ValueError("LlmConfig.model_name is required and cannot be empty.")
        if not isinstance(config.temperature, (int, float)) or not (0.0 <= config.temperature <= 2.0):
            raise ValueError("LlmConfig.temperature must be between 0.0 and 2.0.")

        self._llm: ChatAnthropic = ChatAnthropic(
            model=config.model_name,
            api_key=config.api_key,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
        )
        self._parser = StrOutputParser()

    def build_chain(self, prompt_template: ChatPromptTemplate):
        return prompt_template | self._llm | self._parser

    def invoke(self, message: list[BaseMessage]) -> str:
        return self._parser.invoke(self._llm.invoke(message))
