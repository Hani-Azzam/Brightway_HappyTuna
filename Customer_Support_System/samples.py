"""
Smoke-test for the sentiment scorer and activity logging.
Uses its own throwaway database file so repeated runs never
pollute or depend on the real customer_support.db.

Run directly:  python samples.py
"""
import os

# Point storage at a dedicated test DB *before* importing storage,
# so init_db() creates tables there instead of the real database.
TEST_DB = "samples_test.db"
if os.path.exists(TEST_DB):
    os.remove(TEST_DB)
os.environ["CS_DB_PATH"] = TEST_DB

import storage  # noqa: E402  (must come after setting CS_DB_PATH)
from models import TicketCreate, IssueType, TicketPriority  # noqa: E402

SAMPLES = [
    # All three angry keywords present
    TicketCreate(
        customer_id="CUST-1001",
        issue_type=IssueType.safety_concern,
        subject="Metal fragment in canned tuna",
        description=(
            "this is absolutely DISGUSTING, I got SICK after eating this, UNACCEPTABLE. "
            "Found something sharp in batch 4471."
        ),
        linked_product_batch="4471",
        priority=TicketPriority.high,
    ),
    # Caps + punctuation
    TicketCreate(
        customer_id="CUST-1002",
        issue_type=IssueType.safety_concern,
        subject="Contaminated product",
        description=(
            "The can looked CONTAMINATED and smelled AWFUL. "
            "Threw it away immediately — felt this was DANGEROUS."
        ),
        linked_product_batch="4471",
        priority=TicketPriority.critical,
    ),
    # Positive — multi-word phrase + single word
    TicketCreate(
        customer_id="CUST-1003",
        issue_type=IssueType.general,
        subject="Compliment",
        description=(
            "Just wanted to say thank you — your customer service was great "
            "and the replacement arrived fast."
        ),
    ),
    # Neutral — plain factual complaint
    TicketCreate(
        customer_id="CUST-1004",
        issue_type=IssueType.delivery,
        subject="Order not arrived",
        description=(
            "My order from Monday has not arrived yet. "
            "The tracking number shows no movement since Tuesday."
        ),
    ),
    # Edge case: "ill" is a substring of "billing" — should NOT fire angry
    TicketCreate(
        customer_id="CUST-1005",
        issue_type=IssueType.billing,
        subject="Duplicate billing charge",
        description=(
            "I was charged twice for my last order. "
            "Please refund the duplicate billing charge."
        ),
    ),
    # Frustrated — single keyword
    TicketCreate(
        customer_id="CUST-1006",
        issue_type=IssueType.delivery,
        subject="Still waiting on refund",
        description=(
            "This is absolutely ridiculous — I've been waiting three weeks "
            "and nobody has responded to my emails."
        ),
    ),
    # Frustrated — multi-word phrase
    TicketCreate(
        customer_id="CUST-1007",
        issue_type=IssueType.general,
        subject="No response from support",
        description="I submitted a ticket five days ago and I'm still waiting. Not acceptable.",
    ),
    # Negation: "not sick" should NOT fire angry
    TicketCreate(
        customer_id="CUST-1008",
        issue_type=IssueType.quality,
        subject="Product fine actually",
        description=(
            "I was worried at first but I'm not sick and the product tasted normal. "
            "Just wanted to flag it."
        ),
    ),
    # keyword_v1 limit: negation more than 2 tokens away is NOT caught.
    # "don't" is 3 tokens before "disgusting", so the scorer still fires angry.
    # This is the documented boundary of the 2-token negation window.
    TicketCreate(
        customer_id="CUST-1009",
        issue_type=IssueType.quality,
        subject="Minor texture concern",
        description="I don't find it disgusting, just a bit off. Not a big deal.",
    ),
]

EXPECTED = [
    "angry", "angry", "positive", "neutral", "neutral",
    "frustrated", "frustrated", "neutral", "angry",
]


def main() -> None:
    print(f"Using throwaway test database: {TEST_DB}\n")
    print(f"{'ID':<12} {'Expected':<10} {'Got':<10} {'Match':<6}  Description snippet")
    print("-" * 80)
    all_pass = True
    first_ticket_id = None
    for data, expected in zip(SAMPLES, EXPECTED):
        ticket = storage.create_ticket(data)
        if first_ticket_id is None:
            first_ticket_id = ticket.ticket_id
        got = ticket.sentiment.value if hasattr(ticket.sentiment, "value") else ticket.sentiment
        match = got == expected
        if not match:
            all_pass = False
        snippet = data.description[:55].replace("\n", " ")
        flag = "OK" if match else "FAIL"
        print(f"{ticket.ticket_id:<12} {expected:<10} {got:<10} {flag:<6}  {snippet!r}")

    print()
    log = storage.get_activity_log(first_ticket_id)
    print(f"Activity log for {first_ticket_id} ({len(log)} entries):")
    for entry in log:
        print(f"  [{entry.log_id}] {entry.activity_type:<18} actor={entry.actor}  details={entry.details}")

    print()
    print("All samples passed." if all_pass else "SOME SAMPLES FAILED -- see FAIL rows above.")

    # Clean up the throwaway DB so re-runs always start fresh
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


if __name__ == "__main__":
    main()