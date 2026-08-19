import os
from base.tool_base import ToolBase, ToolSchema, ToolResult

CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
COLLECTION_NAME = "journalist"


class SearchKnowledgeTool(ToolBase):
    """
    Searches the Journalist's Chroma DB knowledge base to investigate a claim
    or find background context before writing.

    The knowledge base is pre-loaded with:
    - Past food safety crises and salmonella cases
    - How recalls work step by step
    - Regulatory rules and timelines
    - HappyTuna company background
    - Example investigative journalism pieces
    - Food industry standards and inspection procedures

    The Journalist uses this to:
    - Investigate a claim by finding similar past events
    - Add factual background context to an article
    - Verify whether a claim is consistent with known facts
    - Find precedents (e.g. how similar recalls played out)
    - Decide how serious a situation is based on past cases
    """

    def __init__(self, document_store=None):
        """
        document_store: an already-initialised DocumentStore instance
        connected to the journalist Chroma collection.
        If None, a lazy connection is attempted on first run().
        """
        self._store = document_store

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="search_knowledge",
            description=(
                "Search the journalist knowledge base for background information "
                "on a topic. Use this to INVESTIGATE A CLAIM before writing — "
                "find past cases, regulatory context, industry standards, or "
                "factual background that supports or challenges the claim. "
                "Always call this before publishing an investigative article. "
                "Returns the most relevant documents from the knowledge base."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "What you want to investigate or find background on. "
                            "Be specific. "
                            "e.g. 'salmonella contamination canned food recall procedures', "
                            "'how long does a food safety investigation take', "
                            "'HappyTuna production history', "
                            "'legal obligations company during food recall'."
                        ),
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return. Default 3, max 6.",
                    },
                },
                "required": ["query"],
            },
        )

    def run(self, **kwargs) -> ToolResult:
        query = kwargs["query"]
        top_k = min(int(kwargs.get("top_k", 3)), 6)

        if self._store is None:
            return ToolResult(
                error=(
                    "Knowledge base not initialised. "
                    "DocumentStore must be passed to SearchKnowledgeTool."
                )
            )

        try:
            results = self._store.retrieve(query, top_k=top_k)

            if not results:
                return ToolResult(
                    value=(
                        f"No relevant documents found for '{query}'. "
                        f"The knowledge base may not have information on this topic yet."
                    )
                )

            # Format results clearly for the LLM
            lines = [f"Knowledge base results for '{query}' ({len(results)} found):\n"]
            for i, r in enumerate(results, 1):
                source = r.document.metadata.get("source", "unknown source")
                score = round(r.score, 3)
                content = r.document.page_content.strip()
                lines.append(
                    f"[{i}] Source: {source} | Relevance: {score}\n"
                    f"{content[:500]}"
                    f"{'...' if len(content) > 500 else ''}\n"
                )
            print(lines)
            return ToolResult(value="\n".join(lines))

        except Exception as e:
            return ToolResult(
                error=f"Knowledge base search failed: {e}",
                is_idempotent=True,
            )
