import os
import httpx
from base.tool_base import ToolBase, ToolSchema, ToolResult



class SearchNewsTool(ToolBase):
    """
    Searches The Daily Catch for existing articles by keyword.
    The Journalist uses this to:
    - Check if a story has already been covered before publishing
    - Find background context on a topic
    - Avoid duplicating a story already published
    - Track how the crisis narrative is developing
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="search_news",
            description=(
                "Search The Daily Catch news website for articles matching a keyword. "
                "Use this BEFORE publishing to check if the story has been covered. "
                "Also use this to find background context on any topic. "
                "Returns titles, summaries, and publication times of matching articles."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search keyword or phrase. "
                            "e.g. 'salmonella', 'HappyTuna recall', 'production line shutdown'."
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results to return. Default 5, max 20.",
                    },
                },
                "required": ["query"],
            },
        )

    def run(self, **kwargs) -> ToolResult:

        NEWS_URL = os.getenv("NEWS_URL", "http://localhost:8003")  # ← moved here
        query = kwargs["query"]
        limit = kwargs.get("limit", 5)

        try:
            r = httpx.get(
                f"{NEWS_URL}/articles/search",
                params={"q": query, "limit": limit},
                timeout=10,
            )
            r.raise_for_status()
            articles = r.json()

            if not articles:
                return ToolResult(
                    value=f"No articles found matching '{query}'. This topic has not been covered yet."
                )

            # Format results clearly for the LLM to read
            lines = [f"Found {len(articles)} article(s) matching '{query}':\n"]
            for i, a in enumerate(articles, 1):
                lines.append(
                    f"{i}. [{a.get('category', '?').upper()}] {a.get('title')}\n"
                    f"   Author: {a.get('author')} | Published: {a.get('published_at', '?')[:10]}\n"
                    f"   {a.get('body', '')[:200]}...\n"
                )
            return ToolResult(value="\n".join(lines))

        except httpx.HTTPStatusError as e:
            return ToolResult(error=f"News website error: {e.response.status_code}")
        except Exception as e:
            return ToolResult(error=f"Failed to reach news website: {e}")