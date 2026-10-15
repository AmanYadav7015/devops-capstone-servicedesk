import { useCallback, useEffect, useMemo, useState } from "react";

import StatsBar from "./components/StatsBar";
import TicketCard from "./components/TicketCard";
import TicketForm from "./components/TicketForm";
import { ApiError, API_BASE, api } from "./api";
import { slaState } from "./sla";
import { STATUSES } from "./types";
import type { Category, Stats, Ticket, TicketDraft, TicketPatch } from "./types";

type StatusFilter = "ALL" | (typeof STATUSES)[number] | "BREACHING";

const FILTERS: { value: StatusFilter; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "OPEN", label: "Open" },
  { value: "PENDING", label: "Pending" },
  { value: "RESOLVED", label: "Resolved" },
  { value: "CLOSED", label: "Closed" },
  { value: "BREACHING", label: "SLA breached" },
];

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("ALL");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [ticketList, categoryList, summary] = await Promise.all([
        api.listTickets(),
        api.listCategories(),
        api.stats(),
      ]);
      setTickets(ticketList);
      setCategories(categoryList);
      setStats(summary);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unexpected error loading the queue");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function guard(action: () => Promise<string>): Promise<boolean> {
    setBusy(true);
    try {
      const message = await action();
      await refresh();
      setNotice(message);
      setError(null);
      return true;
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The request could not be completed");
      return false;
    } finally {
      setBusy(false);
    }
  }

  const createTicket = (draft: TicketDraft) =>
    guard(async () => {
      const created = await api.createTicket(draft);
      return `Ticket #${created.id} created`;
    });

  const patchTicket = (id: number, patch: TicketPatch) =>
    guard(async () => {
      await api.updateTicket(id, patch);
      return `Ticket #${id} updated`;
    });

  const removeTicket = (ticket: Ticket) =>
    guard(async () => {
      await api.deleteTicket(ticket.id);
      return `Ticket #${ticket.id} deleted`;
    });

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return tickets.filter((ticket) => {
      if (filter === "BREACHING" && !slaState(ticket).breached) {
        return false;
      }
      if (filter !== "ALL" && filter !== "BREACHING" && ticket.status !== filter) {
        return false;
      }
      if (!needle) {
        return true;
      }
      return (
        ticket.subject.toLowerCase().includes(needle) ||
        ticket.description.toLowerCase().includes(needle) ||
        ticket.requester.toLowerCase().includes(needle) ||
        ticket.assignee.toLowerCase().includes(needle)
      );
    });
  }, [tickets, filter, search]);

  const counts = useMemo(() => {
    const result: Record<string, number> = {
      ALL: tickets.length,
      BREACHING: tickets.filter((ticket) => slaState(ticket).breached).length,
    };
    for (const status of STATUSES) {
      result[status] = tickets.filter((ticket) => ticket.status === status).length;
    }
    return result;
  }, [tickets]);

  return (
    <div className="app">
      <header className="masthead">
        <div className="masthead__brand">
          <span className="logo" aria-hidden="true" />
          <div>
            <h1>ServiceDesk</h1>
            <p>IT support queue — raise, triage and resolve incidents</p>
          </div>
        </div>
        <div className="masthead__operator">
          <span className="operator__name">Aman Yadav</span>
          <span className="operator__role">Service desk operator</span>
          <span className="operator__api">API {API_BASE || "same origin"}</span>
        </div>
      </header>

      <main className="layout">
        <StatsBar stats={stats} />

        {error && (
          <div className="banner banner--error" role="alert">
            <strong>Problem:</strong> {error}
            <button type="button" className="button button--ghost" onClick={() => void refresh()}>
              Retry
            </button>
          </div>
        )}
        {notice && (
          <div className="banner banner--ok" role="status">
            {notice}
          </div>
        )}

        <TicketForm categories={categories} busy={busy} onCreate={createTicket} />

        <section className="toolbar" aria-label="Filter the queue">
          <div className="chips" role="group">
            {FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                className={`chip${filter === item.value ? " chip--active" : ""}`}
                aria-pressed={filter === item.value}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
                <span className="chip__count">{counts[item.value] ?? 0}</span>
              </button>
            ))}
          </div>
          <input
            className="search"
            type="search"
            placeholder="Search subject, requester or assignee"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            aria-label="Search tickets"
          />
        </section>

        {loading ? (
          <p className="placeholder">Loading the ServiceDesk queue…</p>
        ) : visible.length === 0 ? (
          <p className="placeholder">
            No tickets match this view. Clear the filter or raise a new ticket.
          </p>
        ) : (
          <div className="queue">
            {visible.map((ticket) => (
              <TicketCard
                key={ticket.id}
                ticket={ticket}
                categories={categories}
                busy={busy}
                onPatch={patchTicket}
                onDelete={removeTicket}
              />
            ))}
          </div>
        )}
      </main>

      <footer className="sitefoot">
        <span>ServiceDesk · DevOps capstone</span>
        <span>
          {visible.length} of {tickets.length} tickets shown
        </span>
      </footer>
    </div>
  );
}
