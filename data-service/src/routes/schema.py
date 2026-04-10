"""
schema.py — /rest/v1/schema  (schema introspection routes)
Also exposes /rest/v1/sql for SELECT-only raw SQL.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..dependencies import CurrentUser, DbDep
from ..schema_inspector import describe_table, get_full_schema, list_user_tables

router = APIRouter(prefix="/rest/v1", tags=["Schema"])


@router.get("/schema")
async def full_schema(pool: DbDep, current_user: CurrentUser) -> JSONResponse:
    """Returns all user-accessible tables with column metadata."""
    data = await get_full_schema(pool)
    return JSONResponse(content=data)


@router.get("/schema/{table}")
async def table_schema(
    table: str, pool: DbDep, current_user: CurrentUser
) -> JSONResponse:
    """Returns column metadata for a specific table."""
    cols = await describe_table(pool, table)
    if not cols:
        raise HTTPException(status_code=404, detail=f"Table '{table}' not found")
    return JSONResponse(content={"table": table, "columns": cols})


# ── SELECT-only SQL editor ────────────────────────────────────────────────

class SqlRequest(BaseModel):
    query: str


@router.post("/sql")
async def run_sql(
    body: SqlRequest,
    pool: DbDep,
    current_user: CurrentUser,
) -> JSONResponse:
    """
    Execute a read-only SQL query. Only SELECT statements are permitted.
    Tenant isolation is the caller's responsibility here (power-user feature).
    """
    stripped = body.query.strip().upper()
    if not stripped.startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SELECT statements are allowed in the SQL editor",
        )
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(body.query)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = []
    for row in rows:
        d = {}
        for key in row.keys():
            val = row[key]
            d[key] = str(val) if not isinstance(val, (int, float, bool, str, type(None))) else val
        result.append(d)

    return JSONResponse(content={"rows": result, "count": len(result)})
