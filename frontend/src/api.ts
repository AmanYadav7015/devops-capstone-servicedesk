import type { Category, Stats, Ticket, TicketDraft, TicketPatch } from "./types";

const configured = import.meta.env.VITE_API_BASE_URL ?? "";
export const API_BASE = configured.replace(/\/+$/, "");

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function describe(status: number, payload: unknown): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => {
          if (item && typeof item === "object" && "msg" in item) {
            const loc = "loc" in item && Array.isArray(item.loc) ? item.loc.slice(1).join(".") : "";
            const msg = String((item as { msg: unknown }).msg);
            return loc ? `${loc}: ${msg}` : msg;
          }
          return String(item);
        })
        .filter(Boolean);
      if (parts.length > 0) {
        return parts.join("; ");
      }
    }
  }
  return `Request failed with status ${status}`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(0, "Cannot reach the ServiceDesk API");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  const payload: unknown = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, describe(response.status, payload));
  }
  return payload as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  listCategories: () => request<Category[]>("/api/categories"),
  createCategory: (name: string, description: string) =>
    request<Category>("/api/categories", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),
  listTickets: () => request<Ticket[]>("/api/tickets"),
  stats: () => request<Stats>("/api/tickets/stats"),
  getTicket: (id: number) => request<Ticket>(`/api/tickets/${id}`),
  createTicket: (draft: TicketDraft) =>
    request<Ticket>("/api/tickets", { method: "POST", body: JSON.stringify(draft) }),
  updateTicket: (id: number, patch: TicketPatch) =>
    request<Ticket>(`/api/tickets/${id}`, { method: "PUT", body: JSON.stringify(patch) }),
  deleteTicket: (id: number) => request<void>(`/api/tickets/${id}`, { method: "DELETE" }),
};
