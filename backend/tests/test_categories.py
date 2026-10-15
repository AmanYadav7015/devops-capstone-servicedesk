from fastapi.testclient import TestClient


def test_category_list_starts_empty(client: TestClient) -> None:
    response = client.get("/api/categories")

    assert response.status_code == 200
    assert response.json() == []


def test_create_category_returns_201_and_the_new_row(client: TestClient) -> None:
    response = client.post(
        "/api/categories",
        json={"name": "Network", "description": "VPN, Wi-Fi and firewall incidents"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Network"
    assert body["description"] == "VPN, Wi-Fi and firewall incidents"
    assert isinstance(body["id"], int)

    listed = client.get("/api/categories").json()
    assert [item["name"] for item in listed] == ["Network"]


def test_duplicate_category_name_returns_409(client: TestClient) -> None:
    first = client.post("/api/categories", json={"name": "Access"})
    assert first.status_code == 201

    duplicate = client.post("/api/categories", json={"name": "Access"})

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "Category already exists"
    assert len(client.get("/api/categories").json()) == 1


def test_empty_category_name_returns_422(client: TestClient) -> None:
    response = client.post("/api/categories", json={"name": ""})

    assert response.status_code == 422
    assert client.get("/api/categories").json() == []


def test_categories_are_listed_alphabetically(client: TestClient) -> None:
    for name in ("Software", "Access", "Network", "Hardware"):
        assert client.post("/api/categories", json={"name": name}).status_code == 201

    names = [item["name"] for item in client.get("/api/categories").json()]

    assert names == ["Access", "Hardware", "Network", "Software"]
