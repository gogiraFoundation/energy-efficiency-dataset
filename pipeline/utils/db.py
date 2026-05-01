import os
from dataclasses import dataclass

import psycopg2
from psycopg2 import OperationalError
from psycopg2.extras import DictCursor


def _connection_refused_hint(config: "DbConfig", exc: OperationalError) -> str:
    return (
        f"Cannot reach PostgreSQL at {config.host}:{config.port} ({exc}).\n"
        "  • If you use Docker: start Docker Desktop, then start the DB container, e.g.\n"
        "      docker start uk-energy-pg\n"
        "      docker ps   # should show 0.0.0.0:55432->5432/tcp (or your host port)\n"
        "  • Or from repo root: docker compose up -d\n"
        "  • Match .env to the published port: UK_ENERGY_DB_PORT must equal the host port (e.g. 55432).\n"
        "  • Or point elsewhere: UK_ENERGY_DB_HOST, UK_ENERGY_DB_PORT, UK_ENERGY_DB_NAME, UK_ENERGY_DB_USER"
    )


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    dbname: str
    user: str
    password_env_var: str
    connect_timeout: int = 10


class PostgresClient:
    def __init__(self, config: DbConfig):
        password = os.getenv(config.password_env_var)
        if not password:
            raise ValueError(f"Missing DB password env var: {config.password_env_var}")
        self.config = config
        try:
            self._conn = psycopg2.connect(
                host=config.host,
                port=config.port,
                dbname=config.dbname,
                user=config.user,
                password=password,
                connect_timeout=config.connect_timeout,
                cursor_factory=DictCursor,
            )
        except OperationalError as e:
            msg = str(e).lower()
            if "connection refused" in msg or "could not connect" in msg:
                raise ConnectionError(_connection_refused_hint(config, e)) from e
            raise
        self._conn.autocommit = False

    def execute(self, sql: str, params=None) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)

    def fetchall(self, sql: str, params=None):
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def execute_file(self, file_path: str) -> None:
        with open(file_path, "r", encoding="utf-8") as f:
            sql = f.read()
        with self._conn.cursor() as cur:
            cur.execute(sql)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()
