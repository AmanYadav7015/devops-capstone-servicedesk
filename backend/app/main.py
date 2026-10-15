from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .db import Base, engine, get_db
from .models import Category, Ticket
from .schemas import (
    CategoryCreate,
    CategoryOut,
    StatsOut,
    TicketCreate,
    TicketOut,
    TicketUpdate,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
def root():
    return {"service": settings.app_name, "version": settings.app_version, "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "UP"}


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(select(func.count(Ticket.id)))
    return {"status": "READY"}


@app.get("/api/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name)))


@app.post("/api/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Category).where(Category.name == payload.name)):
        raise HTTPException(status_code=409, detail="Category already exists")
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(db: Session = Depends(get_db)):
    return list(db.scalars(select(Ticket).order_by(Ticket.id.desc())))


@app.get("/api/tickets/stats", response_model=StatsOut)
def stats(db: Session = Depends(get_db)):
    rows = db.execute(select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)).all()
    counts = {s: c for s, c in rows}
    breaching = db.scalar(
        select(func.count(Ticket.id)).where(
            Ticket.sla_due_at < datetime.now(timezone.utc),
            Ticket.status.in_(("OPEN", "PENDING")),
        )
    )
    return StatsOut(
        total=sum(counts.values()),
        open=counts.get("OPEN", 0),
        pending=counts.get("PENDING", 0),
        resolved=counts.get("RESOLVED", 0),
        closed=counts.get("CLOSED", 0),
        breachingSla=breaching or 0,
    )


@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@app.post("/api/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, db: Session = Depends(get_db)):
    if payload.category_id is not None and not db.get(Category, payload.category_id):
        raise HTTPException(status_code=422, detail="Category not found")
    ticket = Ticket(**payload.model_dump())
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.put("/api/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: int, payload: TicketUpdate, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("category_id") is not None and not db.get(Category, data["category_id"]):
        raise HTTPException(status_code=422, detail="Category not found")
    for key, value in data.items():
        setattr(ticket, key, value)
    db.commit()
    db.refresh(ticket)
    return ticket


@app.delete("/api/tickets/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    db.delete(ticket)
    db.commit()
