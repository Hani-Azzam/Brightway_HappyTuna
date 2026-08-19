from base.tool_base import ToolBase, ToolResult, ToolSchema
from services import mail_client

_MAX_SUBJECT_LEN = 200
_MAX_BODY_LEN = 4000


class SendEmail(ToolBase):

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="Send_Email",
            description=(
                "Send an email to another agent in the BitriX world. "
                "Use this when you want to formally communicate with another agent such as "
                "the CEO, COO, board members, regulators, journalists, customers, or employees. "
                "Emails are persistent and will appear in the recipient's inbox."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "from_address": {
                        "type": "string",
                        "description": "Your own BitriX email address (e.g. ceo@happytuna.bitrix).",
                    },
                    "to_address": {
                        "type": "string",
                        "description": "The recipient's BitriX email address (e.g. coo@happytuna.bitrix).",
                    },
                    "subject": {
                        "type": "string",
                        "description": "A short subject line for the email.",
                        "maxLength": _MAX_SUBJECT_LEN,
                    },
                    "body": {
                        "type": "string",
                        "description": "The full body text of the email.",
                        "maxLength": _MAX_BODY_LEN,
                    },
                },
                "required": ["from_address", "to_address", "subject", "body"],
            },
        )

    def run(
        self,
        from_address: str,
        to_address: str,
        subject: str,
        body: str,
    ) -> ToolResult:
        if not from_address or not to_address:
            return ToolResult(
                error="Both from_address and to_address are required.",
                is_idempotent=False,
            )
        if not subject:
            return ToolResult(
                error="A subject line is required.",
                is_idempotent=False,
            )
        if not body:
            return ToolResult(
                error="Email body cannot be empty.",
                is_idempotent=False,
            )

        try:
            email_id = mail_client.send_email(
                from_addr=from_address,
                to_addr=to_address,
                subject=subject,
                body=body,
            )
            return ToolResult(
                value=f"Email sent successfully. ID: {email_id}",
                is_idempotent=False,
            )
        except Exception as exc:
            return ToolResult(
                error=f"Failed to send email: {exc}",
                is_idempotent=False,
            )
