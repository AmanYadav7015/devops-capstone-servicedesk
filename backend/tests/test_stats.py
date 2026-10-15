from fastapi.testclient import TestClient


def test_stats_on_an_empty_queue_are_all_zero(client: TestClient) -> None:
    response = client.get("/api/tickets/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 0,
        "open": 0,
        "pending": 0,
        "resolved": 0,
        "closed": 0,
        "breachingSla": 0,
    }


def test_stats_count_every_status_bucket(client: TestClient, ticket_factory) -> None:
    ticket_factory(subject="Laptop will not boot", status="OPEN")
    ticket_factory(subject="VPN drops every ten minutes", status="OPEN")
    ticket_factory(subject="New joiner needs billing access", status="PENDING")
    ticket_factory(subject="Design licence expired", status="RESOLVED")
    ticket_factory(subject="Third floor printer jams", status="CLOSED")

    response = client.get("/api/tickets/stats")

    assert response.status_code == 200
    assert response.json() == {
        "total": 5,
        "open": 2,
        "pending": 1,
        "resolved": 1,
        "closed": 1,
        "breachingSla": 0,
    }


def test_stats_count_a_ticket_whose_sla_has_already_passed(
    client: TestClient, ticket_factory
) -> None:
    ticket_factory(subject="Within its SLA window", status="OPEN", sla_hours_from_now=24)
    assert client.get("/api/tickets/stats").json()["breachingSla"] == 0

    ticket_factory(
        subject="Mail relay queue backed up for six hours",
        status="OPEN",
        sla_hours_from_now=-3,
    )

    body = client.get("/api/tickets/stats").json()

    assert body["breachingSla"] == 1
    assert body["total"] == 2
    assert body["open"] == 2


def test_stats_count_a_breaching_pending_ticket(client: TestClient, ticket_factory) -> None:
    ticket_factory(subject="Waiting on the vendor past the SLA", status="PENDING", sla_hours_from_now=-8)

    body = client.get("/api/tickets/stats").json()

    assert body["breachingSla"] == 1
    assert body["pending"] == 1


def test_stats_ignore_past_due_tickets_that_are_resolved_or_closed(
    client: TestClient, ticket_factory
) -> None:
    ticket_factory(subject="Archived disk alert", status="RESOLVED", sla_hours_from_now=-48)
    ticket_factory(subject="Old badge request", status="CLOSED", sla_hours_from_now=-72)

    body = client.get("/api/tickets/stats").json()

    assert body["total"] == 2
    assert body["resolved"] == 1
    assert body["closed"] == 1
    assert body["breachingSla"] == 0


def test_resolving_a_breaching_ticket_clears_the_breach_count(
    client: TestClient, ticket_factory
) -> None:
    ticket = ticket_factory(
        subject="Mail relay queue backed up for six hours",
        status="OPEN",
        sla_hours_from_now=-3,
    )
    assert client.get("/api/tickets/stats").json()["breachingSla"] == 1

    assert client.put(f"/api/tickets/{ticket.id}", json={"status": "RESOLVED"}).status_code == 200

    body = client.get("/api/tickets/stats").json()

    assert body["breachingSla"] == 0
    assert body["resolved"] == 1
    assert body["open"] == 0


def test_stats_follow_create_and_delete(client: TestClient) -> None:
    created = client.post("/api/tickets", json={"subject": "Monitor flickers on the left port"})
    assert created.status_code == 201
    assert client.get("/api/tickets/stats").json()["total"] == 1

    assert client.delete(f"/api/tickets/{created.json()['id']}").status_code == 204

    assert client.get("/api/tickets/stats").json()["total"] == 0
