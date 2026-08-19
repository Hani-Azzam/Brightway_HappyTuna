import os
import httpx
from base.tool_base import ToolBase, ToolSchema, ToolResult



class PublishArticleTool(ToolBase):
    """
    Publishes a finished article to The Daily Catch news website.
    This is the Journalist's primary output action — called only after
    investigation and fact-checking are complete.
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="publish_article",
            description=(
                "Publish a news article to The Daily Catch. "
                "Call this ONLY when the article is fully written and fact-checked. "
                "Use category 'breaking' for urgent unfolding events, "
                "'investigative' for deep research pieces, "
                "'update' for follow-ups, "
                "'opinion' for editorial analysis."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "The article headline — clear, factual, attention-grabbing.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Full article text. Use newlines to separate paragraphs. "
                            "Include who, what, when, where, why. "
                            "Cite sources where possible."
                        ),
                    },
                    "category": {
                        "type": "string",
                        "enum": ["breaking", "investigative", "update", "opinion"],
                        "description": "Article category — determines placement and urgency on the site.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keyword tags e.g. ['HappyTuna', 'salmonella', 'recall'].",
                    },
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "URLs or sources investigated before writing this article.",
                    },
                },
                "required": ["title", "body", "category"],
            },
        )

    def run(self, **kwargs) -> ToolResult:

        NEWS_URL = os.getenv("NEWS_URL", "http://localhost:8003")
        title = kwargs["title"]
        body = kwargs["body"]
        category = kwargs["category"]
        tags = kwargs.get("tags", [])
        source_urls = kwargs.get("source_urls", [])

        try:
            r = httpx.post(
                f"{NEWS_URL}/articles",
                json={
                    "title": title,
                    "body": body,
                    "author": "Journalist Agent",
                    "category": category,
                    "tags": tags,
                    "source_urls": source_urls,
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            return ToolResult(
                value=(
                    f"Article published successfully. "
                    f"ID: {data.get('id')} | "
                    f"Published at: {data.get('published_at')} | "
                    f"Title: {data.get('title')}"
                ),
                is_idempotent=False,  # publishing has a real side effect
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                error=f"News website rejected the article: {e.response.status_code} — {e.response.text}",
                is_idempotent=False,
            )
        except Exception as e:
            return ToolResult(
                error=f"Failed to reach news website: {e}",
                is_idempotent=True,  # safe to retry if connection failed
            )