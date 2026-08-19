"""Internal Messaging System (Internal Chat) — a BitriX business-system surface.

A standalone service agents talk *through*: no LLM, no reasoning. It stores
channels + messages, enforces membership, labels untrusted content, and is
reachable over the wire via MCP (`chat.*` tools) and REST.

See docs/internal_chat_v2_design.md. Built strictly on the COO `mcp_core`
contract, the non-chat KB/roles/tools docs, and the social-network surface
pattern — it does not reuse any prior internal-chat code.
"""
