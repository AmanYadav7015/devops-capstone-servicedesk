from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import conftest
from app import db as app_db
from app.main import app


def test_the_suite_never_points_at_the_production_database() -> None:
    assert conftest.TEST_DATABASE_URL
    assert conftest.TEST_DATABASE_URL != conftest.PRODUCTION_DATABASE_URL

    if conftest.PRODUCTION_DATABASE_URL:
        assert "_test" in conftest.TEST_DATABASE_URL or conftest.TEST_DATABASE_URL.startswith(
            "sqlite"
        )


def test_the_application_engine_is_bound_to_the_test_database() -> None:
    assert app_db.engine.url.render_as_string(hide_password=False) == str(
        conftest.test_engine.url.render_as_string(hide_password=False)
    )


def test_get_db_is_overridden_while_a_test_client_is_active(
    client: TestClient, db_session: Session
) -> None:
    assert app_db.get_db in app.dependency_overrides

    override = app.dependency_overrides[app_db.get_db]
    generator = override()
    try:
        assert next(generator) is db_session
    finally:
        generator.close()

    assert client.get("/health").status_code == 200


def test_each_test_starts_from_an_empty_queue(client: TestClient) -> None:
    assert client.get("/api/tickets").json() == []
    assert client.get("/api/categories").json() == []

    assert client.post("/api/tickets", json={"subject": "Left behind on purpose"}).status_code == 201
    assert len(client.get("/api/tickets").json()) == 1


def test_the_previous_tests_rows_do_not_leak_into_this_one(client: TestClient) -> None:
    assert client.get("/api/tickets").json() == []
    assert client.get("/api/tickets/stats").json()["total"] == 0
