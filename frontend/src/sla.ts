import type { Ticket } from "./types";

const ACTIVE = new Set(["OPEN", "PENDING"]);

export interface SlaState {
  breached: boolean;
  label: string;
}

export function slaState(ticket: Ticket, now: number = Date.now()): SlaState {
  const due = new Date(ticket.sla_due_at).getTime();
  const remaining = due - now;
  const active = ACTIVE.has(ticket.status);

  if (!active) {
    return { breached: false, label: ticket.status === "CLOSED" ? "SLA closed" : "SLA met" };
  }
  if (remaining <= 0) {
    return { breached: true, label: `SLA breached ${humanise(-remaining)} ago` };
  }
  return { breached: false, label: `SLA due in ${humanise(remaining)}` };
}

export function humanise(milliseconds: number): string {
  const minutes = Math.max(1, Math.round(milliseconds / 60000));
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 48) {
    return `${hours}h`;
  }
  return `${Math.round(hours / 24)}d`;
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  return date.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
