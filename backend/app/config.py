import os


def _normalise(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


class Settings:
    app_name: str = os.getenv("APP_NAME", "ServiceDesk API")
    app_version: str = os.getenv("APP_VERSION", "1.1.0")
    database_url: str = _normalise(
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://servicedesk:servicedesk@localhost:5432/servicedesk",
        )
    )


settings = Settings()
