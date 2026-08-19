"""
MCP server for the Customer Support system.

Exposes the same operations as the REST API (main.py), but as MCP tools
for agents (Customer, Influencer, COO, etc.) to call directly, instead of
making raw HTTP requests.

Both this MCP server and the REST API (main.py) call the same storage.py
functions, sharing the same SQLite database -- a ticket created via an
MCP tool call shows up in the dashboard immediately, and vice versa.

Run standalone:
    python mcp_server.py

Runs on streamable-http transport so agents in other containers can
reach it over the network (stdio transport only works for local
parent/child process pairs, not cross-container calls).
"""
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

import storage
from models import TicketCreate, TicketPatch, IssueType, TicketPriority

mcp = FastMCP(
    name="customer-support",
    host="0.0.0.0",
    port=int(os.environ.get("MCP_PORT", 8010)),
)


@mcp.tool()
def create_ticket(
    customer_id: str,
    issue_type: str,
    subject: str,
    description: str,
    linked_product_batch: Optional[str] = None,
    priority: str = "medium",
) -> dict:
    """Create a new customer support ticket.

    Sentiment is scored automatically from the description text -- do not
    pass sentiment yourself.

    Args:
        customer_id: The id of the customer agent filing this ticket.
        issue_type: One of: quality, delivery, billing, general, safety_concern.
            Use safety_concern for contamination, foreign objects, illness,
            swollen cans, or allergen mislabeling -- anything that should be
            treated as an escalation-worthy safety signal.
        subject: A short one-line summary of the complaint.
        description: The full complaint text, written the way the customer
            would actually say it. This is what the system uses to score
            sentiment (angry / frustrated / neutral / positive).
        linked_product_batch: The batch/lot number if the customer mentioned
            or is reacting to one, otherwise omit.
        priority: One of: low, medium, high, critical. Defaults to medium.

    Returns:
        The created ticket, including its ticket_id and auto-scored sentiment.
    """
    data = TicketCreate(
        customer_id=customer_id,
        issue_type=IssueType(issue_type),
        subject=subject,
        description=description,
        linked_product_batch=linked_product_batch,
        priority=TicketPriority(priority),
    )
    ticket = storage.create_ticket(data)
    return ticket.model_dump(mode="json")


@mcp.tool()
def get_ticket(ticket_id: str) -> dict:
    """Fetch a single ticket by its id.

    Args:
        ticket_id: The ticket id, e.g. "TCK-00001".

    Returns:
        The ticket if found, or an object with an "error" key if not found.
    """
    ticket = storage.get_ticket(ticket_id)
    if ticket is None:
        return {"error": f"Ticket {ticket_id!r} not found"}
    return ticket.model_dump(mode="json")


@mcp.tool()
def list_tickets(
    customer_id: Optional[str] = None,
    status: Optional[str] = None,
    issue_type: Optional[str] = None,
    linked_product_batch: Optional[str] = None,
) -> dict:
    """List tickets, optionally filtered. All filters are optional and combinable.

    Args:
        customer_id: Only tickets filed by this customer.
        status: One of: open, in_progress, escalated, resolved, closed.
        issue_type: One of: quality, delivery, billing, general, safety_concern.
        linked_product_batch: Only tickets referencing this batch number --
            useful for checking how many complaints exist about a specific batch.

    Returns:
        An object with "count" and "tickets" (a list of matching tickets,
        newest first).
    """
    tickets = storage.list_tickets(
        customer_id=customer_id,
        status=status,
        issue_type=issue_type,
        linked_product_batch=linked_product_batch,
    )
    return {
        "count": len(tickets),
        "tickets": [t.model_dump(mode="json") for t in tickets],
    }


@mcp.tool()
def patch_ticket(
    ticket_id: str,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    assignee: Optional[str] = None,
    reply_message: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict:
    """Update a ticket. Only the fields you pass are changed; omit the rest.

    Every changed field is automatically recorded in the ticket's activity
    log -- you never need to log anything yourself.

    Args:
        ticket_id: The ticket to update.
        status: New status: open, in_progress, escalated, resolved, closed.
        priority: New priority: low, medium, high, critical.
        assignee: Who now owns this ticket (e.g. "COO-1").
        reply_message: A reply to send to the customer.
        actor: Who is making this change (e.g. "COO-1"). Defaults to "system"
            if omitted.

    Returns:
        The updated ticket, or an object with an "error" key if not found.
    """
    patch_kwargs = {}
    if status is not None:
        patch_kwargs["status"] = status
    if priority is not None:
        patch_kwargs["priority"] = priority
    if assignee is not None:
        patch_kwargs["assignee"] = assignee
    if reply_message is not None:
        patch_kwargs["reply_message"] = reply_message
    if actor is not None:
        patch_kwargs["actor"] = actor

    patch = TicketPatch(**patch_kwargs)
    updated = storage.patch_ticket(ticket_id, patch)
    if updated is None:
        return {"error": f"Ticket {ticket_id!r} not found"}
    return updated.model_dump(mode="json")


@mcp.tool()
def get_activity_log(ticket_id: str) -> dict:
    """Get the full activity history for a ticket, oldest first.

    Args:
        ticket_id: The ticket whose history to fetch.

    Returns:
        An object with "count" and "entries" (activity log entries such as
        created, status_changed, assigned, replied, sentiment_scored,
        sorted chronologically).
    """
    log = storage.get_activity_log(ticket_id)
    return {
        "count": len(log),
        "entries": [e.model_dump(mode="json") for e in log],
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
