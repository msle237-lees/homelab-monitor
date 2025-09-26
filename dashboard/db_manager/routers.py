# Routers for the 'machines' table with automatic TIMESTAMP refresh on updates.

from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, Query, Form, Path

from deps import get_db

router = APIRouter()


# ----------------------------
# helpers
# ----------------------------
async def _exists(db: aiosqlite.Connection, machine_id: str) -> bool:
    cur = await db.execute("SELECT 1 FROM machines WHERE MACHINE_ID = ?;", (machine_id,))
    row = await cur.fetchone()
    await cur.close()
    return row is not None


# ----------------------------
# machines
# ----------------------------
@router.post("/machines", tags=["machines"])
async def create_machine(
    MACHINE_ID: str = Form(...),
    MACHINE_NAME: str = Form(...),
    CPU_CORES: int = Form(...),
    RAM_USED: int = Form(...),
    RAM_TOTAL: int = Form(...),
    STORAGE_USED: int = Form(...),
    STORAGE_TOTAL: int = Form(...),
    CPU_TEMPS: float = Form(...),
    NETWORK_USAGE: int = Form(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Upsert-like behavior: if exists, replace row; else insert new.
    if await _exists(db, MACHINE_ID):
        await db.execute(
            """
            UPDATE machines
               SET MACHINE_NAME = ?, CPU_CORES = ?, RAM_USED = ?, RAM_TOTAL = ?,
                   STORAGE_USED = ?, STORAGE_TOTAL = ?, CPU_TEMPS = ?, NETWORK_USAGE = ?,
                   TIMESTAMP = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE MACHINE_ID = ?;
            """,
            (
                MACHINE_NAME, CPU_CORES, RAM_USED, RAM_TOTAL,
                STORAGE_USED, STORAGE_TOTAL, CPU_TEMPS, NETWORK_USAGE,
                MACHINE_ID,
            ),
        )
    else:
        await db.execute(
            """
            INSERT INTO machines (
                MACHINE_ID, MACHINE_NAME, CPU_CORES, RAM_USED, RAM_TOTAL,
                STORAGE_USED, STORAGE_TOTAL, CPU_TEMPS, NETWORK_USAGE
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                MACHINE_ID, MACHINE_NAME, CPU_CORES, RAM_USED, RAM_TOTAL,
                STORAGE_USED, STORAGE_TOTAL, CPU_TEMPS, NETWORK_USAGE,
            ),
        )
    await db.commit()

    cur = await db.execute("SELECT * FROM machines WHERE MACHINE_ID = ?;", (MACHINE_ID,))
    row = await cur.fetchone()
    await cur.close()
    return dict(row)


@router.put("/machines/{machine_id}", tags=["machines"])
async def update_machine(
    machine_id: str = Path(..., description="MACHINE_ID"),
    MACHINE_NAME: Optional[str] = Form(None),
    CPU_CORES: Optional[int] = Form(None),
    RAM_USED: Optional[int] = Form(None),
    RAM_TOTAL: Optional[int] = Form(None),
    STORAGE_USED: Optional[int] = Form(None),
    STORAGE_TOTAL: Optional[int] = Form(None),
    CPU_TEMPS: Optional[float] = Form(None),
    NETWORK_USAGE: Optional[int] = Form(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not await _exists(db, machine_id):
        raise HTTPException(404, "machine not found")

    fields = []
    args = []
    for col, val in [
        ("MACHINE_NAME", MACHINE_NAME),
        ("CPU_CORES", CPU_CORES),
        ("RAM_USED", RAM_USED),
        ("RAM_TOTAL", RAM_TOTAL),
        ("STORAGE_USED", STORAGE_USED),
        ("STORAGE_TOTAL", STORAGE_TOTAL),
        ("CPU_TEMPS", CPU_TEMPS),
        ("NETWORK_USAGE", NETWORK_USAGE),
    ]:
        if val is not None:
            fields.append(f"{col} = ?")
            args.append(val)

    # Always refresh TIMESTAMP on update — even if no other fields were supplied.
    fields.append("TIMESTAMP = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))")

    args.append(machine_id)
    await db.execute(f"UPDATE machines SET {', '.join(fields)} WHERE MACHINE_ID = ?;", args)
    await db.commit()

    cur = await db.execute("SELECT * FROM machines WHERE MACHINE_ID = ?;", (machine_id,))
    row = await cur.fetchone()
    await cur.close()
    return dict(row)


@router.get("/machines", tags=["machines"])
async def list_machines(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    name: Optional[str] = Query(None, alias="machine_name"),
    db: aiosqlite.Connection = Depends(get_db),
):
    where = ""
    args = []
    if name:
        where = "WHERE MACHINE_NAME = ?"
        args.append(name)

    cur = await db.execute(f"SELECT COUNT(*) FROM machines {where};", args)
    (total,) = await cur.fetchone()
    await cur.close()

    cur = await db.execute(
        f"SELECT * FROM machines {where} ORDER BY MACHINE_NAME ASC LIMIT ? OFFSET ?;",
        [*args, limit, offset],
    )
    rows = [dict(r) for r in await cur.fetchall()]
    await cur.close()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


@router.get("/machines/{machine_id}", tags=["machines"])
async def get_machine(machine_id: str, db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute("SELECT * FROM machines WHERE MACHINE_ID = ?;", (machine_id,))
    row = await cur.fetchone()
    await cur.close()
    if not row:
        raise HTTPException(404, "machine not found")
    return dict(row)


@router.delete("/machines/{machine_id}", status_code=204, tags=["machines"])
async def delete_machine(machine_id: str, db: aiosqlite.Connection = Depends(get_db)):
    cur = await db.execute("DELETE FROM machines WHERE MACHINE_ID = ?;", (machine_id,))
    await db.commit()
    if cur.rowcount == 0:
        raise HTTPException(404, "machine not found")
