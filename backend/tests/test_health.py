from fastapi.testclient import TestClient


def test_root_banner_identifies_the_servicedesk_api(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ServiceDesk API"
    assert body["version"] == "1.1.0"
    assert body["docs"] == "/docs"


def test_health_endpoint_reports_up(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}


def test_ready_endpoint_queries_the_database(client: TestClient, ticket_factory) -> None:
    ticket_factory(subject="Readiness probe needs a row to count")

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "READY"}


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    client.get("/health")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "# HELP http_requests_total" in response.text
    assert "# TYPE http_requests_total counter" in response.text


def test_unknown_route_returns_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
