import os
import tempfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

PRODUCTION_DATABASE_URL = os.environ.get("DATABASE_URL", "")

_TMP_DIR = tempfile.mkdtemp(prefix="servicedesk-tests-")
_SQLITE_FALLBACK = f"sqlite+pysqlite:///{os.path.join(_TMP_DIR, 'servicedesk_test.sqlite3')}"


def _ensure_postgres_database(url: URL) -> bool:
    maintenance = url.set(database="postgres")
    try:
        admin = create_engine(maintenance, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": url.database},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{url.database}"'))
        admin.dispose()
        return True
    except sqlalchemy.exc.SQLAlchemyError:
        return False


def _resolve_test_database_url() -> str:
    configured = os.environ.get("TEST_DATABASE_URL", "").strip()
    if configured:
        url = make_url(configured)
        if url.get_backend_name() == "postgresql" and not _ensure_postgres_database(url):
            raise RuntimeError(f"TEST_DATABASE_URL is not reachable: {url.render_as_string()}")
        return configured

    if PRODUCTION_DATABASE_URL:
        url = make_url(PRODUCTION_DATABASE_URL)
        if url.get_backend_name() == "postgresql" and url.database:
            candidate = url.set(database=f"{url.database}_test")
            if _ensure_postgres_database(candidate):
                return candidate.render_as_string(hide_password=False)

    return _SQLITE_FALLBACK


TEST_DATABASE_URL = _resolve_test_database_url()

if PRODUCTION_DATABASE_URL and TEST_DATABASE_URL == PRODUCTION_DATABASE_URL:
    raise RuntimeError(
        "Refusing to run the test suite against the production database. "
        "TEST_DATABASE_URL must differ from DATABASE_URL."
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Category, Ticket  # noqa: E402

connect_args = {"check_same_thread": False} if TEST_DATABASE_URL.startswith("sqlite") else {}
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


@pytest.fixture(scope="session", autouse=True)
def schema() -> Iterator[None]:
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture
def db_session() -> Iterator[Session]:
    with test_engine.begin() as connection:
        connection.execute(Ticket.__table__.delete())
        connection.execute(Category.__table__.delete())
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def category_factory(db_session: Session):
    def make(name: str = "Hardware", description: str = "") -> Category:
        category = Category(name=name, description=description)
        db_session.add(category)
        db_session.commit()
        db_session.refresh(category)
        return category

    return make


@pytest.fixture
def ticket_factory(db_session: Session):
    def make(
        subject: str = "Keyboard not detected on the docking station",
        status: str = "OPEN",
        severity: str = "MEDIUM",
        category_id: int | None = None,
        sla_hours_from_now: float = 24.0,
        requester: str = "Priya Nair",
        assignee: str = "Aman Yadav",
    ) -> Ticket:
        now = datetime.now(timezone.utc)
        ticket = Ticket(
            subject=subject,
            description="Raised by the ServiceDesk test suite",
            status=status,
            severity=severity,
            requester=requester,
            assignee=assignee,
            category_id=category_id,
            created_at=now,
            sla_due_at=now + timedelta(hours=sla_hours_from_now),
        )
        db_session.add(ticket)
        db_session.commit()
        db_session.refresh(ticket)
        return ticket

    return make
