import { useEffect, useState } from "react";

import { formatTimestamp, slaState } from "../sla";
import { SEVERITIES, STATUSES } from "../types";
import type { Category, Severity, Status, Ticket, TicketPatch } from "../types";

interface Props {
  ticket: Ticket;
  categories: Category[];
  busy: boolean;
  onPatch: (id: number, patch: TicketPatch) => Promise<boolean>;
  onDelete: (ticket: Ticket) => Promise<boolean>;
}

export default function TicketCard({ ticket, categories, busy, onPatch, onDelete }: Props) {
  const [assignee, setAssignee] = useState(ticket.assignee);
  const sla = slaState(ticket);
  const category = categories.find((item) => item.id === ticket.category_id);

  useEffect(() => {
    setAssignee(ticket.assignee);
  }, [ticket.assignee]);

  function commitAssignee() {
    const next = assignee.trim() || "Unassigned";
    if (next === ticket.assignee) {
      setAssignee(ticket.assignee);
      return;
    }
    void onPatch(ticket.id, { assignee: next });
  }

  return (
    <article className={`ticket ticket--${ticket.severity.toLowerCase()}`} data-testid="ticket">
      <header className="ticket__head">
        <div className="ticket__title">
          <span className="ticket__id">#{ticket.id}</span>
          <h3>{ticket.subject}</h3>
        </div>
        <div className="ticket__badges">
          <span className={`badge badge--${ticket.severity.toLowerCase()}`}>{ticket.severity}</span>
          <span className={`badge badge--status-${ticket.status.toLowerCase()}`}>
            {ticket.status}
          </span>
          <span className={`badge ${sla.breached ? "badge--breach" : "badge--muted"}`}>
            {sla.label}
          </span>
        </div>
      </header>

      {ticket.description && <p className="ticket__body">{ticket.description}</p>}

      <dl className="ticket__meta">
        <div>
          <dt>Category</dt>
          <dd>{category ? category.name : "Uncategorised"}</dd>
        </div>
        <div>
          <dt>Requester</dt>
          <dd>{ticket.requester}</dd>
        </div>
        <div>
          <dt>Raised</dt>
          <dd>{formatTimestamp(ticket.created_at)}</dd>
        </div>
        <div>
          <dt>SLA due</dt>
          <dd>{formatTimestamp(ticket.sla_due_at)}</dd>
        </div>
      </dl>

      <footer className="ticket__controls">
        <label className="control">
          <span>Status</span>
          <select
            value={ticket.status}
            disabled={busy}
            onChange={(event) => void onPatch(ticket.id, { status: event.target.value as Status })}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className="control">
          <span>Severity</span>
          <select
            value={ticket.severity}
            disabled={busy}
            onChange={(event) =>
              void onPatch(ticket.id, { severity: event.target.value as Severity })
            }
          >
            {SEVERITIES.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>

        <label className="control">
          <span>Category</span>
          <select
            value={ticket.category_id ?? ""}
            disabled={busy}
            onChange={(event) =>
              void onPatch(ticket.id, {
                category_id: event.target.value ? Number(event.target.value) : null,
              })
            }
          >
            <option value="">No category</option>
            {categories.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </label>

        <label className="control control--grow">
          <span>Assignee</span>
          <input
            value={assignee}
            disabled={busy}
            maxLength={120}
            onChange={(event) => setAssignee(event.target.value)}
            onBlur={commitAssignee}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.currentTarget.blur();
              }
            }}
          />
        </label>

        <button
          type="button"
          className="button button--danger"
          disabled={busy}
          onClick={() => void onDelete(ticket)}
        >
          Delete
        </button>
      </footer>
    </article>
  );
}
