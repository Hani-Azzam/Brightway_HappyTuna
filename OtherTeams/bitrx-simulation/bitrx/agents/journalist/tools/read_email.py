import os
import httpx
from base.tool_base import ToolBase, ToolSchema, ToolResult

EMAIL_URL = os.getenv("EMAIL_URL", "http://email:8010")


class ReadEmailTool(ToolBase):
    """
    Reads incoming emails from the Journalist's inbox.
    Used to check for replies from sources after sending interview requests.
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_email",
            description=(
                "Check the journalist inbox for new emails or replies from sources. "
                "Use this AFTER sending an email to check if the recipient responded. "
                "Returns a list of emails with sender, subject, and body."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "from_sender": {
                        "type": "string",
                        "description": "Optional. Filter emails by sender address e.g. 'ceo@happytuna.com'.",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, return only unread emails. Default true.",
                    },
                },
                "required": [],
            },
        )

    def run(self, **kwargs) -> ToolResult:
        EMAIL_URL = os.getenv("EMAIL_URL", "http://localhost:8010")
        from_sender = kwargs.get("from_sender", "")
        unread_only = kwargs.get("unread_only", True)

        try:
            params = {
                "inbox": "journalist@thedailycatch.com",
                "unread_only": unread_only,
            }
            if from_sender:
                params["from"] = from_sender

            r = httpx.get(
                f"{EMAIL_URL}/inbox",
                params=params,
                timeout=10,
            )
            r.raise_for_status()
            emails = r.json()

            if not emails:
                return ToolResult(
                    value="No new emails in inbox. Sources have not replied yet."
                )

            lines = [f"Found {len(emails)} email(s) in inbox:\n"]
            for i, email in enumerate(emails, 1):
                lines.append(
                    f"{i}. From: {email.get('from')} | Subject: {email.get('subject')}\n"
                    f"   {email.get('body', '')[:300]}\n"
                )
            return ToolResult(value="\n".join(lines))

        except httpx.ConnectError:
            return ToolResult(
                value="[Email system offline — cannot check inbox. Proceeding without replies.]"
            )
        except Exception as e:
            return ToolResult(
                error=f"Failed to read inbox: {e}",
                is_idempotent=True,
            )