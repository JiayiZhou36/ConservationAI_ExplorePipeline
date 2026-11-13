"""One small SQL interface: SQLite locally, PostgreSQL when DATABASE_URL is set."""
import sqlite3
from contextlib import contextmanager


class Database:
    def __init__(self, local_path, url=None):
        self.local_path = str(local_path)
        self.url = url
        self.postgres = bool(url)
        if self.postgres and not url.startswith(("postgresql://", "postgres://")):
            raise ValueError("DATABASE_URL must be a PostgreSQL connection URL")

    @contextmanager
    def connect(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            # Disable automatic prepared statements for transaction-pool compatibility.
            connection = psycopg.connect(self.url, row_factory=dict_row,
                                         prepare_threshold=None, connect_timeout=15)
        else:
            connection = sqlite3.connect(self.local_path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield SQLSession(connection, self.postgres)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class SQLSession:
    def __init__(self, connection, postgres):
        self.connection = connection
        self.postgres = postgres

    def execute(self, sql, parameters=()):
        # Application SQL uses ? placeholders and contains no literal ? operators.
        query = sql.replace("?", "%s") if self.postgres else sql
        return self.connection.execute(query, parameters)

    def executescript(self, script):
        # For our fixed schema only: no functions/triggers or semicolons in literals.
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
