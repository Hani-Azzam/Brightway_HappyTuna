// ============================================================
// CS Monitor — HappyTuna Customer Support Dashboard · Team 3
// ============================================================
// Change BASE_URL to match your Docker port when not running locally.
// ============================================================

import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Fish, RefreshCw, AlertTriangle, Inbox,
  ChevronRight, Activity, MessageSquare,
  CircleDot, ArrowLeftRight, UserCheck,
  MessageSquareReply, Zap, Clock,
} from "lucide-react";

const BASE_URL = "http://localhost:8003";

// ============================================================
// 1. CONSTANTS + HELPERS
// ============================================================

const STATUS = {
  open:        { bg: "#fef3c7", text: "#92400e", bar: "#f59e0b", label: "Open" },
  in_progress: { bg: "#dbeafe", text: "#1e40af", bar: "#3b82f6", label: "In progress" },
  escalated:   { bg: "#fee2e2", text: "#991b1b", bar: "#ef4444", label: "Escalated" },
  resolved:    { bg: "#dcfce7", text: "#166534", bar: "#22c55e", label: "Resolved" },
  closed:      { bg: "#f1f5f9", text: "#64748b", bar: "#cbd5e1", label: "Closed" },
};

const ISSUE = {
  safety_concern: { bg: "#fee2e2", text: "#991b1b", label: "Safety concern" },
  quality:        { bg: "#ede9fe", text: "#5b21b6", label: "Quality" },
  delivery:       { bg: "#dbeafe", text: "#1e40af", label: "Delivery" },
  billing:        { bg: "#e0e7ff", text: "#3730a3", label: "Billing" },
  general:        { bg: "#f1f5f9", text: "#64748b", label: "General" },
};

const PRIORITY = {
  low:      { bg: "#f1f5f9", text: "#64748b" },
  medium:   { bg: "#dbeafe", text: "#1e40af" },
  high:     { bg: "#ffedd5", text: "#9a3412" },
  critical: { bg: "#fee2e2", text: "#991b1b" },
};

const SENTIMENT = {
  angry:      { bg: "#fee2e2", text: "#991b1b" },
  frustrated: { bg: "#ffedd5", text: "#9a3412" },
  neutral:    { bg: "#f1f5f9", text: "#64748b" },
  positive:   { bg: "#dcfce7", text: "#166534" },
};

const ACTIVITY_DOT = {
  created:         "#6366f1",
  status_changed:  "#8b5cf6",
  priority_changed:"#f59e0b",
  assigned:        "#22c55e",
  replied:         "#06b6d4",
  sentiment_scored:"#f97316",
};

const ACTIVITY_ICON = {
  created:         <CircleDot size={12} />,
  status_changed:  <ArrowLeftRight size={12} />,
  priority_changed:<AlertTriangle size={12} />,
  assigned:        <UserCheck size={12} />,
  replied:         <MessageSquareReply size={12} />,
  sentiment_scored:<Zap size={12} />,
};

const FILTER_DEFAULTS = { status: "", issue_type: "", sentiment: "", batch: "" };

function label(str) {
  if (!str) return "—";
  return str.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

function timeAgo(iso) {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ============================================================
// 2. SMALL COMPONENTS
// ============================================================

function Pill({ value, map }) {
  const c = map?.[value] ?? { bg: "#f1f5f9", text: "#64748b" };
  return (
    <span style={{
      display: "inline-flex", alignItems: "center",
      padding: "3px 9px", borderRadius: 20,
      fontSize: 11, fontWeight: 600,
      background: c.bg, color: c.text,
      whiteSpace: "nowrap",
    }}>
      {c.label ?? label(value)}
    </span>
  );
}

function MetricCard({ label: lbl, value, alert }) {
  const isAlert = alert && value > 0;
  return (
    <div style={{
      flex: 1, padding: "16px 18px", borderRadius: 12,
      background: isAlert ? "#fff5f5" : "#fff",
      border: `1.5px solid ${isAlert ? "#fecaca" : "#f1f5f9"}`,
    }}>
      <div style={{ fontSize: 28, fontWeight: 700, lineHeight: 1, marginBottom: 4,
        color: isAlert ? "#ef4444" : value > 0 ? "#6366f1" : "#cbd5e1" }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: "#94a3b8", fontWeight: 500,
        textTransform: "uppercase", letterSpacing: "0.05em" }}>
        {lbl}
      </div>
    </div>
  );
}

function FieldRow({ label: lbl, value, mono }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600,
        textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 3 }}>
        {lbl}
      </div>
      <div style={{ fontSize: 12, color: "#334155",
        fontFamily: mono ? "monospace" : "inherit" }}>
        {value || <span style={{ color: "#e2e8f0" }}>—</span>}
      </div>
    </div>
  );
}

function ActivityEntry({ entry, isLast }) {
  const dot = ACTIVITY_DOT[entry.activity_type] ?? "#94a3b8";
  const icon = ACTIVITY_ICON[entry.activity_type];
  const { activity_type: type, actor, details = {} } = entry;

  function body() {
    switch (type) {
      case "created":
        return <>Filed by <strong>{actor}</strong></>;
      case "status_changed":
        return (
          <>
            <span style={{ color: "#94a3b8" }}>{label(details.from)}</span>
            {" → "}
            <strong style={{ color: "#0f172a" }}>{label(details.to)}</strong>
            {" by "}{actor}
          </>
        );
      case "priority_changed":
        return (
          <>
            Priority{" "}
            <span style={{ color: "#94a3b8" }}>{label(details.from)}</span>
            {" → "}
            <strong style={{ color: "#0f172a" }}>{label(details.to)}</strong>
            {" by "}{actor}
          </>
        );
      case "assigned":
        return <>Assigned to <strong>{details.assignee ?? actor}</strong></>;
      case "replied":
        return (
          <>
            Reply by <strong>{actor}</strong>
            {details.message && (
              <div style={{
                marginTop: 6, padding: "8px 12px",
                background: "#f0fdf4",
                borderLeft: "3px solid #22c55e",
                borderRadius: "0 8px 8px 0",
                color: "#166534", fontStyle: "italic",
                fontSize: 12, lineHeight: 1.55,
              }}>
                "{details.message}"
              </div>
            )}
          </>
        );
      case "sentiment_scored":
        return (
          <>
            Sentiment{" "}
            <strong style={{ color: SENTIMENT[details.sentiment]?.text ?? "#64748b" }}>
              {details.sentiment}
            </strong>
            {details.method && (
              <span style={{ color: "#94a3b8" }}> · {details.method}</span>
            )}
          </>
        );
      default:
        return <>{label(type)} by <strong>{actor}</strong></>;
    }
  }

  return (
    <div style={{ display: "flex", gap: 12 }}>
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 16, flexShrink: 0 }}>
        <div style={{
          width: 10, height: 10, borderRadius: "50%",
          background: dot, boxShadow: `0 0 0 3px ${dot}22`,
          marginTop: 3, flexShrink: 0,
        }} />
        {!isLast && (
          <div style={{ flex: 1, width: 2, background: "#f1f5f9", marginTop: 4 }} />
        )}
      </div>
      <div style={{ paddingBottom: isLast ? 0 : 20, flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
          <span style={{
            fontSize: 10, fontWeight: 700, color: dot,
            textTransform: "uppercase", letterSpacing: "0.05em",
          }}>
            {label(type)}
          </span>
          <span style={{ fontSize: 10, color: "#94a3b8" }}>
            {fmtDateTime(entry.timestamp)}
          </span>
        </div>
        <div style={{ fontSize: 12, color: "#64748b", lineHeight: 1.55 }}>
          {body()}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// 3. TICKET CARD
// ============================================================

function TicketCard({ ticket, isSelected, onClick }) {
  const s = STATUS[ticket.status] ?? STATUS.closed;
  const isSafety = ticket.issue_type === "safety_concern";

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex", cursor: "pointer", borderRadius: 10,
        border: `1.5px solid ${isSelected ? "#6366f1" : isSafety ? "#fecaca" : "#f1f5f9"}`,
        background: isSelected ? "#fafafe" : "#fff",
        boxShadow: isSelected ? "0 0 0 3px #eef2ff" : "none",
        marginBottom: 8, overflow: "hidden",
        transition: "all .15s",
      }}
    >
      <div style={{ width: 4, flexShrink: 0, background: s.bar }} />
      <div style={{ flex: 1, padding: "12px 14px", minWidth: 0 }}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, marginBottom: 8 }}>
          <div style={{
            fontWeight: 600, fontSize: 13, color: "#0f172a", lineHeight: 1.4,
            overflow: "hidden", display: "-webkit-box",
            WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
          }}>
            {ticket.subject}
          </div>
          <span style={{ fontSize: 11, color: "#94a3b8", whiteSpace: "nowrap", marginTop: 1 }}>
            {timeAgo(ticket.created_at)}
          </span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginBottom: 8 }}>
          <Pill value={ticket.status} map={STATUS} />
          <Pill value={ticket.issue_type} map={ISSUE} />
          {ticket.sentiment && <Pill value={ticket.sentiment} map={SENTIMENT} />}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "#94a3b8" }}>
          <span style={{ fontFamily: "monospace" }}>{ticket.ticket_id}</span>
          {ticket.linked_product_batch && (
            <span style={{
              padding: "1px 7px", borderRadius: 20,
              background: "#eff6ff", color: "#3b82f6",
              fontWeight: 600, fontFamily: "monospace",
            }}>
              #{ticket.linked_product_batch}
            </span>
          )}
          {ticket.assignee && (
            <span style={{ marginLeft: "auto" }}>→ {ticket.assignee}</span>
          )}
        </div>
      </div>
      {isSelected && (
        <div style={{ display: "flex", alignItems: "center", paddingRight: 10, color: "#6366f1" }}>
          <ChevronRight size={14} />
        </div>
      )}
    </div>
  );
}

// ============================================================
// 4. TICKET LIST PANEL
// ============================================================

function TicketList({ tickets, selectedId, onSelect, onRefresh, loading, error }) {
  const sorted = [...tickets].sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: "#0f172a" }}>Tickets</span>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: "1px 8px",
            borderRadius: 20, background: "#eef2ff", color: "#4f46e5",
          }}>
            {tickets.length}
          </span>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          style={{
            display: "flex", alignItems: "center", gap: 5,
            padding: "6px 12px", borderRadius: 8,
            border: "1.5px solid #e2e8f0", background: "#fff",
            fontSize: 12, color: "#64748b", cursor: loading ? "not-allowed" : "pointer",
            fontFamily: "inherit",
          }}
        >
          <RefreshCw size={11} style={{ animation: loading ? "spin 0.9s linear infinite" : "none" }} />
          Refresh
        </button>
      </div>

      {error && (
        <div style={{
          display: "flex", alignItems: "center", gap: 8,
          padding: "10px 14px", marginBottom: 12, borderRadius: 8,
          background: "#fff5f5", border: "1.5px solid #fecaca",
          color: "#991b1b", fontSize: 12, flexShrink: 0,
        }}>
          <AlertTriangle size={13} />
          API offline — make sure the server is running on port 8001
        </div>
      )}

      <div style={{ flex: 1, overflowY: "auto", paddingRight: 4 }}>
        {sorted.length === 0 && !error ? (
          <div style={{
            display: "flex", flexDirection: "column", alignItems: "center",
            justifyContent: "center", height: 220, color: "#cbd5e1",
          }}>
            <Inbox size={36} style={{ marginBottom: 12, opacity: 0.5 }} />
            <span style={{ fontSize: 13 }}>No tickets match the current filters</span>
          </div>
        ) : (
          sorted.map(t => (
            <TicketCard
              key={t.ticket_id}
              ticket={t}
              isSelected={t.ticket_id === selectedId}
              onClick={() => onSelect(t.ticket_id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

// ============================================================
// 5. TICKET DETAIL PANEL
// ============================================================

function TicketDetail({ ticket, activity, activityLoading }) {
  if (!ticket) {
    return (
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center",
        justifyContent: "center", height: "100%", color: "#cbd5e1",
      }}>
        <MessageSquare size={40} style={{ marginBottom: 12, opacity: 0.4 }} />
        <span style={{ fontSize: 13 }}>Select a ticket to view details</span>
      </div>
    );
  }

  const isSafety = ticket.issue_type === "safety_concern";

  return (
    <div style={{ height: "100%", overflowY: "auto", paddingLeft: 24, animation: "fadeIn .2s ease" }}>
      {/* Header */}
      <div style={{ marginBottom: 18 }}>
        <h2 style={{ fontSize: 16, fontWeight: 700, color: "#0f172a", lineHeight: 1.4, marginBottom: 10 }}>
          {ticket.subject}
        </h2>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
          <Pill value={ticket.status} map={STATUS} />
          <Pill value={ticket.priority} map={PRIORITY} />
          <Pill value={ticket.issue_type} map={ISSUE} />
          {ticket.sentiment && <Pill value={ticket.sentiment} map={SENTIMENT} />}
        </div>
      </div>

      {/* Fields grid */}
      <div style={{
        display: "grid", gridTemplateColumns: "1fr 1fr",
        gap: "12px 24px", marginBottom: 16,
        padding: 14, background: "#f8fafc",
        border: "1.5px solid #f1f5f9", borderRadius: 10,
      }}>
        <FieldRow label="Ticket ID" value={ticket.ticket_id} mono />
        <FieldRow label="Customer" value={ticket.customer_id} mono />
        <FieldRow label="Created" value={fmtDateTime(ticket.created_at)} />
        <FieldRow label="Updated" value={fmtDateTime(ticket.updated_at)} />
        <FieldRow label="Assignee" value={ticket.assignee} mono />
        <FieldRow label="Batch" value={ticket.linked_product_batch ? `#${ticket.linked_product_batch}` : null} mono />
      </div>

      {/* Description */}
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
          Description
        </div>
        <div style={{
          padding: "12px 14px", borderRadius: 10,
          background: isSafety ? "#fff5f5" : "#f8fafc",
          border: `1.5px solid ${isSafety ? "#fecaca" : "#f1f5f9"}`,
          fontSize: 13, color: "#475569", lineHeight: 1.65,
        }}>
          {ticket.description}
        </div>
      </div>

      {/* Reply */}
      {ticket.reply_message && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
            Latest reply
          </div>
          <div style={{
            padding: "12px 14px", background: "#f0fdf4",
            borderLeft: "3px solid #22c55e",
            borderRadius: "0 10px 10px 0",
            fontSize: 13, color: "#166534",
            fontStyle: "italic", lineHeight: 1.65,
          }}>
            {ticket.reply_message}
          </div>
        </div>
      )}

      {/* Activity log */}
      <div>
        <div style={{
          display: "flex", alignItems: "center", gap: 7,
          paddingTop: 14, paddingBottom: 12,
          borderTop: "1.5px solid #f1f5f9", marginBottom: 14,
        }}>
          <Activity size={13} color="#94a3b8" />
          <span style={{ fontSize: 10, color: "#94a3b8", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            Activity log
          </span>
        </div>
        {activityLoading ? (
          <span style={{ fontSize: 12, color: "#94a3b8" }}>Loading…</span>
        ) : activity.length === 0 ? (
          <span style={{ fontSize: 12, color: "#94a3b8" }}>No activity recorded yet</span>
        ) : (
          activity.map((e, i) => (
            <ActivityEntry key={e.log_id} entry={e} isLast={i === activity.length - 1} />
          ))
        )}
        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}

// ============================================================
// 6. MAIN DASHBOARD
// ============================================================

export default function Dashboard() {
  const [allTickets,  setAllTickets]  = useState([]);
  const [displayed,   setDisplayed]   = useState([]);
  const [selectedId,  setSelectedId]  = useState(null);
  const [ticket,      setTicket]      = useState(null);
  const [activity,    setActivity]    = useState([]);
  const [actLoading,  setActLoading]  = useState(false);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState(false);
  const [filters,     setFilters]     = useState(FILTER_DEFAULTS);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef(null);

  const stats = {
    total:    allTickets.length,
    open:     allTickets.filter(t => t.status === "open").length,
    escalated:allTickets.filter(t => t.status === "escalated").length,
    safety:   allTickets.filter(t => t.issue_type === "safety_concern").length,
    batch4471:allTickets.filter(t => t.linked_product_batch === "4471").length,
  };

  // ---- Fetch all tickets ----
  const fetchTickets = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(`${BASE_URL}/tickets`);
      if (!res.ok) throw new Error();
      setAllTickets(await res.json());
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  // ---- Apply client-side filters ----
  useEffect(() => {
    const { status, issue_type, sentiment, batch } = filters;
    setDisplayed(allTickets.filter(t =>
      (!status     || t.status     === status)     &&
      (!issue_type || t.issue_type === issue_type) &&
      (!sentiment  || t.sentiment  === sentiment)  &&
      (!batch      || t.linked_product_batch === batch)
    ));
  }, [allTickets, filters]);

  // ---- Initial load ----
  useEffect(() => { fetchTickets(); }, []);

  // ---- Auto-refresh ----
  useEffect(() => {
    clearInterval(intervalRef.current);
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        fetchTickets();
        if (selectedId) fetchActivity(selectedId);
      }, 10_000);
    }
    return () => clearInterval(intervalRef.current);
  }, [autoRefresh, selectedId]);

  // ---- Fetch activity log ----
  const fetchActivity = useCallback(async (id) => {
    if (!id) return;
    setActLoading(true);
    try {
      const res = await fetch(`${BASE_URL}/tickets/${id}/activity`);
      if (!res.ok) throw new Error();
      setActivity(await res.json());
    } catch {
      setActivity([]);
    } finally {
      setActLoading(false);
    }
  }, []);

  // ---- Select a ticket ----
  function selectTicket(id) {
    const next = id === selectedId ? null : id;
    setSelectedId(next);
    if (!next) { setTicket(null); setActivity([]); return; }
    const found = allTickets.find(t => t.ticket_id === next);
    if (found) setTicket(found);
    fetchActivity(next);
  }

  // ---- Keep detail in sync on refresh ----
  useEffect(() => {
    if (!selectedId) return;
    const updated = allTickets.find(t => t.ticket_id === selectedId);
    if (updated) setTicket(updated);
  }, [allTickets, selectedId]);

  function setFilter(key, val) { setFilters(p => ({ ...p, [key]: val })); }
  function clearFilters() { setFilters(FILTER_DEFAULTS); }
  const hasFilters = Object.values(filters).some(Boolean);

  const inputStyle = {
    border: "1.5px solid #e2e8f0", borderRadius: 8,
    padding: "7px 10px", fontSize: 12, color: "#475569",
    background: "#fff", outline: "none", fontFamily: "inherit",
    minWidth: 130, cursor: "pointer",
    transition: "border-color .15s",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", background: "#f8fafc" }}>

      {/* ── TOP BAR ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "0 24px", height: 52, flexShrink: 0,
        background: "#fff", borderBottom: "1.5px solid #f1f5f9",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 28, height: 28, borderRadius: 8, background: "#6366f1",
            display: "flex", alignItems: "center", justifyContent: "center",
          }}>
            <Fish size={14} color="#fff" />
          </div>
          <span style={{ fontSize: 14, fontWeight: 700, color: "#0f172a" }}>Customer Support</span>
          <span style={{
            fontSize: 12, color: "#94a3b8",
            borderLeft: "1.5px solid #f1f5f9",
            paddingLeft: 10, marginLeft: 2,
          }}>
            HappyTuna · Team 3
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Auto-refresh toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
            {autoRefresh && (
              <div style={{
                width: 7, height: 7, borderRadius: "50%",
                background: "#22c55e",
                animation: "pulse 1.5s ease-in-out infinite",
                boxShadow: "0 0 0 2px #dcfce7",
              }} />
            )}
            <span style={{ fontSize: 12, color: "#94a3b8" }}>
              {autoRefresh ? "Live · 10s" : "Auto-refresh"}
            </span>
            <div
              onClick={() => setAutoRefresh(v => !v)}
              style={{
                width: 36, height: 20, borderRadius: 10, cursor: "pointer",
                background: autoRefresh ? "#6366f1" : "#e2e8f0",
                position: "relative", transition: "background .2s",
              }}
            >
              <div style={{
                width: 16, height: 16, borderRadius: "50%", background: "#fff",
                position: "absolute", top: 2,
                left: autoRefresh ? 18 : 2,
                transition: "left .2s",
                boxShadow: "0 1px 3px rgba(0,0,0,.2)",
              }} />
            </div>
          </div>

          <button
            onClick={fetchTickets}
            disabled={loading}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "6px 14px", borderRadius: 8,
              border: "1.5px solid #e2e8f0", background: "#fff",
              fontSize: 12, color: "#64748b",
              cursor: loading ? "not-allowed" : "pointer",
              fontFamily: "inherit",
            }}
          >
            <RefreshCw size={11} style={{ animation: loading ? "spin 0.9s linear infinite" : "none" }} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── METRICS ── */}
      <div style={{ display: "flex", gap: 10, padding: "16px 24px 0", flexShrink: 0 }}>
        <MetricCard label="Total"          value={stats.total} />
        <MetricCard label="Open"           value={stats.open} />
        <MetricCard label="Escalated"      value={stats.escalated}  alert />
        <MetricCard label="Safety concerns"value={stats.safety}     alert />
        <MetricCard label="Batch #4471"    value={stats.batch4471} />
      </div>

      {/* ── FILTERS ── */}
      <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "12px 24px", flexShrink: 0 }}>
        <select style={inputStyle} value={filters.status} onChange={e => setFilter("status", e.target.value)}>
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="in_progress">In progress</option>
          <option value="escalated">Escalated</option>
          <option value="resolved">Resolved</option>
          <option value="closed">Closed</option>
        </select>
        <select style={inputStyle} value={filters.issue_type} onChange={e => setFilter("issue_type", e.target.value)}>
          <option value="">All issue types</option>
          <option value="safety_concern">Safety concern</option>
          <option value="quality">Quality</option>
          <option value="delivery">Delivery</option>
          <option value="billing">Billing</option>
          <option value="general">General</option>
        </select>
        <select style={inputStyle} value={filters.sentiment} onChange={e => setFilter("sentiment", e.target.value)}>
          <option value="">All sentiments</option>
          <option value="angry">Angry</option>
          <option value="frustrated">Frustrated</option>
          <option value="neutral">Neutral</option>
          <option value="positive">Positive</option>
        </select>
        <input
          type="text"
          placeholder="Batch #…"
          value={filters.batch}
          onChange={e => setFilter("batch", e.target.value)}
          style={{ ...inputStyle, width: 100, fontFamily: "monospace", cursor: "text" }}
        />
        {hasFilters && (
          <button
            onClick={clearFilters}
            style={{
              padding: "7px 12px", borderRadius: 8,
              border: "1.5px solid #e2e8f0", background: "#fff",
              fontSize: 12, color: "#94a3b8", cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Clear
          </button>
        )}
        <span style={{ fontSize: 12, color: "#94a3b8", marginLeft: 4 }}>
          {displayed.length} ticket{displayed.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* ── MAIN CONTENT ── */}
      <div style={{ flex: 1, display: "grid", gridTemplateColumns: "1fr 1fr", overflow: "hidden", padding: "0 24px 24px" }}>
        <div style={{ paddingRight: 16, overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <TicketList
            tickets={displayed}
            selectedId={selectedId}
            onSelect={selectTicket}
            onRefresh={fetchTickets}
            loading={loading}
            error={error}
          />
        </div>

        <div style={{ borderLeft: "1.5px solid #f1f5f9", overflow: "hidden", display: "flex", flexDirection: "column" }}>
          <TicketDetail
            ticket={ticket}
            activity={activity}
            activityLoading={actLoading}
          />
        </div>
      </div>
    </div>
  );
}
