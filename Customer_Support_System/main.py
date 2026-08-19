from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

from models import TicketCreate, TicketPatch, TicketStatus, IssueType
import storage

app = FastAPI(title="Customer Support API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/tickets", status_code=201)
def create_ticket(data: TicketCreate):
    return storage.create_ticket(data)


@app.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: str):
    ticket = storage.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")
    return ticket


@app.get("/tickets")
def list_tickets(
    customer_id: Optional[str] = Query(default=None),
    status: Optional[TicketStatus] = Query(default=None),
    issue_type: Optional[IssueType] = Query(default=None),
    linked_product_batch: Optional[str] = Query(default=None),
):
    return storage.list_tickets(
        customer_id=customer_id,
        status=status,
        issue_type=issue_type,
        linked_product_batch=linked_product_batch,
    )


@app.patch("/tickets/{ticket_id}")
def patch_ticket(ticket_id: str, patch: TicketPatch):
    ticket = storage.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")
    return storage.patch_ticket(ticket_id, patch)


@app.get("/tickets/{ticket_id}/activity")
def get_activity(ticket_id: str):
    ticket = storage.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id!r} not found")
    return storage.get_activity_log(ticket_id)
