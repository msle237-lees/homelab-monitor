# Rebase with TIMESTAMP column added to machines table.

import aiosqlite
from typing import Any, List, Optional, Tuple


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None

    async def connect(self):
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self.connection.execute("PRAGMA foreign_keys = ON;")
        await self.connection.commit()

    async def close(self):
        if self.connection:
            await self.connection.close()

    async def execute(self, query: str, params: Tuple = ()) -> None:
        if not self.connection:
            raise RuntimeError("Database connection is not established.")
        await self.connection.execute(query, params)
        await self.connection.commit()

    async def fetchone(self, query: str, params: Tuple = ()) -> Optional[aiosqlite.Row]:
        if not self.connection:
            raise RuntimeError("Database connection is not established.")
        cursor = await self.connection.execute(query, params)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchall(self, query: str, params: Tuple = ()) -> List[aiosqlite.Row]:
        if not self.connection:
            raise RuntimeError("Database connection is not established.")
        cursor = await self.connection.execute(query, params)
        rows = await cursor.fetchall()
        await cursor.close()
        return rows

    async def setup(self):
        schema = """
        CREATE TABLE IF NOT EXISTS machines (
            MACHINE_ID    TEXT PRIMARY KEY,
            MACHINE_NAME  TEXT NOT NULL,
            CPU_CORES     INTEGER NOT NULL,
            RAM_USED      INTEGER NOT NULL,
            RAM_TOTAL     INTEGER NOT NULL,
            STORAGE_USED  INTEGER NOT NULL,
            STORAGE_TOTAL INTEGER NOT NULL,
            CPU_TEMPS     REAL    NOT NULL,
            NETWORK_USAGE INTEGER NOT NULL,
            TIMESTAMP     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );
        """
        if not self.connection:
            raise RuntimeError("Database connection is not established.")
        await self.connection.executescript(schema)
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_machines_name ON machines (MACHINE_NAME);")
        await self.connection.execute("CREATE INDEX IF NOT EXISTS idx_machines_ts ON machines (TIMESTAMP DESC);")
        await self.connection.commit()
