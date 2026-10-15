from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Ticket


def test_create_ticket_returns_201_with_the_documented_defaults(client: TestClient) -> None:
    response = client.post(
        "/api/tickets",
        json={"subject": "Laptop will not power on after the firmware update"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["subject"] == "Laptop will not power on after the firmware update"
    assert body["severity"] == "MEDIUM"
    assert body["status"] == "OPEN"
    assert body["requester"] == "Unassigned"
    assert body["assignee"] == "Unassigned"
    assert body["category_id"] is None
    assert isinstance(body["id"], int)


def test_create_ticket_sets_the_sla_due_date_24_hours_ahead(client: TestClient) -> None:
    response = client.post("/api/tickets", json={"subject": "VPN tunnel keeps renegotiating"})

    assert response.status_code == 201
    body = response.json()
    created = datetime.fromisoformat(body["created_at"])
    due = datetime.fromisoformat(body["sla_due_at"])

    assert timedelta(hours=23, minutes=55) < due - created < timedelta(hours=24, minutes=5)


def test_create_ticket_accepts_an_existing_category(client: TestClient, category_factory) -> None:
    category = category_factory(name="Hardware")

    response = client.post(
        "/api/tickets",
        json={
            "subject": "Docking station will not charge the laptop",
            "severity": "HIGH",
            "status": "PENDING",
            "requester": "Rahul Mehta",
            "assignee": "Aman Yadav",
            "category_id": category.id,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["category_id"] == category.id
    assert body["severity"] == "HIGH"
    assert body["status"] == "PENDING"
    assert body["requester"] == "Rahul Mehta"


def test_tickets_are_listed_newest_first(client: TestClient, ticket_factory) -> None:
    first = ticket_factory(subject="Oldest ticket in the queue")
    second = ticket_factory(subject="Middle ticket in the queue")
    third = ticket_factory(subject="Newest ticket in the queue")

    response = client.get("/api/tickets")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [third.id, second.id, first.id]


def test_get_ticket_by_id_returns_the_stored_row(client: TestClient, ticket_factory) -> None:
    ticket = ticket_factory(subject="Printer jams on duplex jobs", severity="LOW")

    response = client.get(f"/api/tickets/{ticket.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ticket.id
    assert body["subject"] == "Printer jams on duplex jobs"
    assert body["severity"] == "LOW"


def test_get_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.get("/api/tickets/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_update_ticket_changes_status_severity_and_assignee(
    client: TestClient, ticket_factory
) -> None:
    ticket = ticket_factory(subject="Mail relay queue is not draining", status="OPEN")

    response = client.put(
        f"/api/tickets/{ticket.id}",
        json={"status": "RESOLVED", "severity": "URGENT", "assignee": "Aman Yadav"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RESOLVED"
    assert body["severity"] == "URGENT"
    assert body["assignee"] == "Aman Yadav"

    reread = client.get(f"/api/tickets/{ticket.id}").json()
    assert reread["status"] == "RESOLVED"
    assert reread["severity"] == "URGENT"


def test_update_only_touches_the_fields_that_were_sent(
    client: TestClient, ticket_factory
) -> None:
    ticket = ticket_factory(
        subject="Shared drive is read only", severity="HIGH", requester="Sana Kapoor"
    )

    response = client.put(f"/api/tickets/{ticket.id}", json={"status": "PENDING"})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["severity"] == "HIGH"
    assert body["subject"] == "Shared drive is read only"
    assert body["requester"] == "Sana Kapoor"


def test_update_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.put("/api/tickets/99999", json={"status": "CLOSED"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_delete_ticket_returns_204_and_the_id_becomes_404(
    client: TestClient, ticket_factory
) -> None:
    ticket = ticket_factory(subject="Temporary ticket raised to prove DELETE")

    deleted = client.delete(f"/api/tickets/{ticket.id}")

    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(f"/api/tickets/{ticket.id}").status_code == 404
    assert client.get("/api/tickets").json() == []


def test_delete_missing_ticket_returns_404(client: TestClient) -> None:
    response = client.delete("/api/tickets/99999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Ticket not found"


def test_create_ticket_with_unknown_category_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/tickets",
        json={"subject": "Ticket pointing at a category that does not exist", "category_id": 99999},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Category not found"
    assert client.get("/api/tickets").json() == []


def test_update_ticket_with_unknown_category_returns_422(
    client: TestClient, ticket_factory
) -> None:
    ticket = ticket_factory(subject="Badge reader offline at the side entrance")

    response = client.put(f"/api/tickets/{ticket.id}", json={"category_id": 99999})

    assert response.status_code == 422
    assert response.json()["detail"] == "Category not found"
    assert client.get(f"/api/tickets/{ticket.id}").json()["category_id"] is None


def test_create_ticket_with_an_invalid_severity_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/tickets",
        json={"subject": "Ticket with an invalid severity", "severity": "CATASTROPHIC"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "severity"]


def test_create_ticket_with_an_invalid_status_returns_422(client: TestClient) -> None:
    response = client.post(
        "/api/tickets",
        json={"subject": "Ticket with an invalid status", "status": "ON_FIRE"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "status"]


def test_create_ticket_without_a_subject_returns_422(client: TestClient) -> None:
    response = client.post("/api/tickets", json={"description": "no subject supplied"})

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing"


def test_ticket_is_linked_to_its_category_row_through_the_foreign_key(
    client: TestClient, db_session: Session, category_factory
) -> None:
    category = category_factory(name="Network", description="VPN and connectivity")

    created = client.post(
        "/api/tickets",
        json={"subject": "Site to site tunnel is flapping", "category_id": category.id},
    )
    assert created.status_code == 201

    stored = db_session.get(Ticket, created.json()["id"])
    assert stored is not None
    assert stored.category is not None
    assert stored.category.name == "Network"
    assert [item.id for item in category.tickets] == [stored.id]


def test_sla_due_at_round_trips_through_the_api(client: TestClient, ticket_factory) -> None:
    ticket = ticket_factory(subject="Backup job missed its window", sla_hours_from_now=-2)

    body = client.get(f"/api/tickets/{ticket.id}").json()
    due = datetime.fromisoformat(body["sla_due_at"])
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)

    assert due < datetime.now(timezone.utc)
