export const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"] as const;
export const STATUSES = ["OPEN", "PENDING", "RESOLVED", "CLOSED"] as const;

export type Severity = (typeof SEVERITIES)[number];
export type Status = (typeof STATUSES)[number];

export interface Category {
  id: number;
  name: string;
  description: string;
}

export interface Ticket {
  id: number;
  subject: string;
  description: string;
  severity: Severity;
  status: Status;
  requester: string;
  assignee: string;
  category_id: number | null;
  created_at: string;
  sla_due_at: string;
}

export interface TicketDraft {
  subject: string;
  description: string;
  severity: Severity;
  status: Status;
  requester: string;
  assignee: string;
  category_id: number | null;
}

export interface TicketPatch {
  subject?: string;
  description?: string;
  severity?: Severity;
  status?: Status;
  requester?: string;
  assignee?: string;
  category_id?: number | null;
}

export interface Stats {
  total: number;
  open: number;
  pending: number;
  resolved: number;
  closed: number;
  breachingSla: number;
}
