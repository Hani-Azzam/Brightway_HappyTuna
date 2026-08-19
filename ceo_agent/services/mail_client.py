"""
HTTP client for the BitriX Mail API (services/email_api.py).

`pop_unread_as_context` is meant to be called by the orchestrator loop
(main.py) BEFORE an agent's turn, not by the LLM as a tool — that's the
whole point: receiving mail is a flow-level concern, not something the
model opts into.
"""

import os

import requests

_BASE_URL = os.getenv("EMAIL_API_URL", "http://127.0.0.1:8000")
_TIMEOUT = 5


def send_email(from_addr: str, to_addr: str, subject: str, body: str) -> str:
    resp = requests.post(
        f"{_BASE_URL}/emails",
        json={"from_addr": from_addr, "to_addr": to_addr, "subject": subject, "body": body},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def fetch_unread(address: str) -> list[dict]:
    resp = requests.get(f"{_BASE_URL}/emails/{address}/unread", timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_inbox(address: str) -> list[dict]:
    resp = requests.get(f"{_BASE_URL}/emails/{address}", timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def count_unread(address: str) -> int:
    resp = requests.get(f"{_BASE_URL}/emails/{address}/unread/count", timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()["count"]


def mark_read(email_id: str) -> None:
    resp = requests.post(f"{_BASE_URL}/emails/{email_id}/read", timeout=_TIMEOUT)
    resp.raise_for_status()


def pop_unread_as_context(address: str) -> str | None:
    """
    Fetch unread emails for `address`, mark them read, and return a formatted
    string ready to prepend to the agent's next prompt. Returns None if there
    is no new mail.
    """
    emails = fetch_unread(address)
    if not emails:
        return None

    for email in emails:
        mark_read(email["id"])

    lines = [f"You have {len(emails)} new email{'s' if len(emails) != 1 else ''} in your inbox:\n"]
    for i, email in enumerate(emails, start=1):
        lines.append(
            f"--- Email {i} ---\n"
            f"From:    {email['from_addr']}\n"
            f"Subject: {email['subject']}\n"
            f"Sent:    {email['sent_at']}\n"
            f"\n{email['body']}"
        )
    return "\n\n".join(lines)
