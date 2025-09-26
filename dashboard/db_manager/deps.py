# Ensure TIMESTAMP column exists in schema.

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite
from fastapi import FastAPI, Request

from database import DatabaseManager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    dbm = DatabaseManager("homelab.db")
    await dbm.connect()

    await dbm.connection.executescript(
        """
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
        CREATE INDEX IF NOT EXISTS idx_machines_name ON machines (MACHINE_NAME);
        CREATE INDEX IF NOT EXISTS idx_machines_ts ON machines (TIMESTAMP DESC);
        """
    )
    await dbm.connection.commit()

    app.state.dbm = dbm
    try:
        yield
    finally:
        await app.state.dbm.close()


async def get_db(request: Request) -> aiosqlite.Connection:
    return request.app.state.dbm.connection
