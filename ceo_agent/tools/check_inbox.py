from base.tool_base import ToolBase, ToolResult, ToolSchema
from services import mail_client


def _format_emails(emails: list[dict]) -> str:
    if not emails:
        return "Inbox is empty."
    lines = []
    for i, email in enumerate(emails, start=1):
        lines.append(
            f"[{i}] From: {email['from_addr']} | Subject: {email['subject']} | Sent: {email['sent_at']}\n"
            f"    {email['body']}"
        )
    return "\n\n".join(lines)


class CheckInbox(ToolBase):

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="Check_Inbox",
            description=(
                "Check your BitriX email inbox for messages. "
                "Use this when you want check if you receive new email and so to read emails you have received from other agents."
                "Set unread_only to true to see only new messages you have not read yet."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Your own BitriX email address (e.g. ceo@happytuna.bitrix).",
                    },
                    "unread_only": {
                        "type": "boolean",
                        "description": "If true, return only unread emails. If false, return all emails.",
                    },
                },
                "required": ["address","unread_only"],
            },
        )

    def run(self, address: str, unread_only: bool = True) -> ToolResult:
        if not address:
            return ToolResult(error="address is required.", is_idempotent=True)

        try:
            if unread_only:
                emails = mail_client.fetch_unread(address)
            else:
                emails = mail_client.fetch_inbox(address)

            for email in emails:
                mail_client.mark_read(email["id"])

            label = "unread " if unread_only else ""
            remaining = mail_client.count_unread(address) if unread_only else None
            header = f"Inbox for {address} ({remaining} {label}email{'s' if remaining != 1 else ''} still)\n\n"
            return ToolResult(value=header + _format_emails(emails), is_idempotent=True)
        except Exception as exc:
            return ToolResult(error=f"Failed to read inbox: {exc}", is_idempotent=True)
