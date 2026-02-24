import os


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    db_name = os.getenv("POSTGRES_POSTGRES_DB")
    db_user = os.getenv("POSTGRES_POSTGRES_USER")
    db_password = os.getenv("POSTGRES_POSTGRES_PASSWORD")
    db_host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    db_port = os.getenv("POSTGRES_PORT", "5432")

    if not db_name or not db_user or not db_password:
        raise RuntimeError(
            "Database config is missing. Set DATABASE_URL or "
            "POSTGRES_POSTGRES_DB/POSTGRES_POSTGRES_USER/POSTGRES_POSTGRES_PASSWORD."
        )

    return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
