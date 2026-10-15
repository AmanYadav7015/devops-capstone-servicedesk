import os


class Settings:
    app_name: str = os.getenv("APP_NAME", "ServiceDesk API")
    app_version: str = os.getenv("APP_VERSION", "1.1.0")
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://servicedesk:servicedesk@localhost:5432/servicedesk"
    )


settings = Settings()
