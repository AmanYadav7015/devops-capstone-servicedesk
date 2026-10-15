from fastapi.testclient import TestClient


def test_health_endpoint_reports_down(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "DOWN"}
