import { useState } from "react";

import { SEVERITIES, STATUSES } from "../types";
import type { Category, Severity, Status, TicketDraft } from "../types";

interface Props {
  categories: Category[];
  busy: boolean;
  onCreate: (draft: TicketDraft) => Promise<boolean>;
}

const EMPTY: TicketDraft = {
  subject: "",
  description: "",
  severity: "MEDIUM",
  status: "OPEN",
  requester: "",
  assignee: "Aman Yadav",
  category_id: null,
};

export default function TicketForm({ categories, busy, onCreate }: Props) {
  const [draft, setDraft] = useState<TicketDraft>(EMPTY);
  const [open, setOpen] = useState(false);

  const change = <K extends keyof TicketDraft>(key: K, value: TicketDraft[K]) =>
    setDraft((current) => ({ ...current, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const payload: TicketDraft = {
      ...draft,
      subject: draft.subject.trim(),
      requester: draft.requester.trim() || "Unassigned",
      assignee: draft.assignee.trim() || "Unassigned",
    };
    if (!payload.subject) {
      return;
    }
    const ok = await onCreate(payload);
    if (ok) {
      setDraft(EMPTY);
      setOpen(false);
    }
  }

  return (
    <section className="panel">
      <button
        type="button"
        className="panel__toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span>{open ? "Close the new ticket form" : "Raise a new ticket"}</span>
        <span aria-hidden="true" className={`chevron${open ? " chevron--open" : ""}`} />
      </button>

      {open && (
        <form className="form" onSubmit={submit}>
          <label className="field field--wide">
            <span>Subject</span>
            <input
              required
              maxLength={200}
              placeholder="Short summary of the issue"
              value={draft.subject}
              onChange={(event) => change("subject", event.target.value)}
            />
          </label>

          <label className="field field--wide">
            <span>Description</span>
            <textarea
              rows={3}
              placeholder="What was the user doing, what did they expect, what happened instead"
              value={draft.description}
              onChange={(event) => change("description", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Severity</span>
            <select
              value={draft.severity}
              onChange={(event) => change("severity", event.target.value as Severity)}
            >
              {SEVERITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Status</span>
            <select
              value={draft.status}
              onChange={(event) => change("status", event.target.value as Status)}
            >
              {STATUSES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Category</span>
            <select
              value={draft.category_id ?? ""}
              onChange={(event) =>
                change("category_id", event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">No category</option>
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Requester</span>
            <input
              maxLength={120}
              placeholder="Who reported it"
              value={draft.requester}
              onChange={(event) => change("requester", event.target.value)}
            />
          </label>

          <label className="field">
            <span>Assignee</span>
            <input
              maxLength={120}
              placeholder="Who owns it"
              value={draft.assignee}
              onChange={(event) => change("assignee", event.target.value)}
            />
          </label>

          <div className="form__actions">
            <button type="submit" className="button button--primary" disabled={busy}>
              {busy ? "Creating…" : "Create ticket"}
            </button>
            <button type="button" className="button" onClick={() => setDraft(EMPTY)}>
              Reset
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
