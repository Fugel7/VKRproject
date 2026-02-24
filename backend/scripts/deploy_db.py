import argparse
import sys
from pathlib import Path

from psycopg import connect
from psycopg.errors import Error as PsycopgError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.db import get_database_url


def deploy_schema(schema_path: Path) -> None:
    # utf-8-sig strips optional BOM, which otherwise breaks SQL parsing in PostgreSQL
    sql = schema_path.read_text(encoding="utf-8-sig")
    with connect(get_database_url(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy PostgreSQL schema for backend.")
    parser.add_argument(
        "--schema",
        default=str(Path(__file__).resolve().parents[1] / "schema.sql"),
        help="Path to schema.sql",
    )
    args = parser.parse_args()

    schema_path = Path(args.schema).resolve()
    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}")
        return 1

    try:
        deploy_schema(schema_path)
    except RuntimeError as exc:
        print(str(exc))
        return 1
    except PsycopgError as exc:
        print(f"Database error: {exc}")
        return 1

    print(f"Schema deployed: {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
