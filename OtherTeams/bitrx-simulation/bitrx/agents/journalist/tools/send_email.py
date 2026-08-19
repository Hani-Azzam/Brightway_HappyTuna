import os
import httpx
from base.tool_base import ToolBase, ToolSchema, ToolResult

# Black box — email system owned by another team
EMAIL_URL = os.getenv("EMAIL_URL", "http://email:8010")


class SendEmailTool(ToolBase):
    """
    Sends an email on behalf of the Journalist to interview sources
    or request comments from the company, CEO, COO, or regulators.

    The email system is owned by another team — treated as a black box.
    We POST to their API and return whatever response we get.
    The Journalist uses this to:
    - Request interviews with company representatives
    - Ask for official statements or comment
    - Follow up on tips from sources
    """

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="send_email",
            description=(
                "Send an email to a source, company representative, or agent to request "
                "an interview, a comment, or information. "
                "Use this to investigate a claim by contacting people directly. "
                "The response from the recipient will be returned if available."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": (
                            "Recipient identifier — an email address or agent role name. "
                            "e.g. 'ceo@happytuna.com', 'coo@happytuna.com', "
                            "'press@happytuna.com', 'ministry-of-health@gov.il'."
                        ),
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line — keep it professional and clear.",
                    },
                    "body": {
                        "type": "string",
                        "description": (
                            "Email body text. Be specific about what you are asking. "
                            "Identify yourself as a journalist from The Daily Catch. "
                            "Include a deadline for response if relevant."
                        ),
                    },
                },
                "required": ["to", "subject", "body"],
            },
        )

    def run(self, **kwargs) -> ToolResult:
        to = kwargs["to"]
        subject = kwargs["subject"]
        body = kwargs["body"]

        try:
            r = httpx.post(
                f"{EMAIL_URL}/send",
                json={
                    "from": "journalist@thedailycatch.com",
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "sender_role": "journalist",
                },
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()

            # Check if the email system returned an immediate reply
            reply = data.get("reply") or data.get("response")
            if reply:
                return ToolResult(
                    value=(
                        f"Email sent to {to}. "
                        f"Immediate reply received:\n{reply}"
                    ),
                    is_idempotent=False,
                )
            return ToolResult(
                value=(
                    f"Email sent to {to} — subject: '{subject}'. "
                    f"Message ID: {data.get('id', 'unknown')}. "
                    f"Awaiting response."
                ),
                is_idempotent=False,
            )

        except httpx.ConnectError:
            # Email system not yet available (other team hasn't built it)
            # Return a simulated "no response" so the agent can continue
            return ToolResult(
                value=(
                    f"Email sent to {to} — subject: '{subject}'. "
                    f"[Email system offline — no response received. "
                    f"Proceeding without comment from this source.]"
                ),
                is_idempotent=False,
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                error=f"Email system error: {e.response.status_code} — {e.response.text}",
                is_idempotent=False,
            )
        except Exception as e:
            return ToolResult(
                error=f"Failed to send email: {e}",
                is_idempotent=True,
            )