from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severity = Literal["LOW", "MEDIUM", "HIGH", "URGENT"]
Status = Literal["OPEN", "PENDING", "RESOLVED", "CLOSED"]


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = ""


class CategoryOut(CategoryCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TicketCreate(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    description: str = ""
    severity: Severity = "MEDIUM"
    status: Status = "OPEN"
    requester: str = "Unassigned"
    assignee: str = "Unassigned"
    category_id: int | None = None


class TicketUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    severity: Severity | None = None
    status: Status | None = None
    requester: str | None = None
    assignee: str | None = None
    category_id: int | None = None


class TicketOut(TicketCreate):
    id: int
    created_at: datetime
    sla_due_at: datetime
    model_config = ConfigDict(from_attributes=True)


class StatsOut(BaseModel):
    total: int
    open: int
    pending: int
    resolved: int
    closed: int
    breachingSla: int
