"""
rest.py — /rest/v1/{table} CRUD routes
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..dependencies import CurrentUser, DbDep, require_table_access
from ..query_builder import (
    build_delete_query,
    build_insert_query,
    build_select_query,
    build_update_query,
)

router = APIRouter(prefix="/rest/v1", tags=["Data API"])


def _rows_to_json(rows: list[asyncpg.Record]) -> list[dict[str, Any]]:
    """Convert asyncpg Records to JSON-serialisable dicts."""
    result = []
    for row in rows:
        d = {}
        for key in row.keys():
            val = row[key]
            # UUIDs and other special types → str
            d[key] = str(val) if not isinstance(val, (int, float, bool, str, type(None))) else val
        result.append(d)
    return result


async def _execute(
    pool: asyncpg.Pool, sql: str, args: list[Any]
) -> list[asyncpg.Record]:
    try:
        async with pool.acquire() as conn:
            return await conn.fetch(sql, *args)
    except asyncpg.UndefinedTableError:
        raise HTTPException(status_code=404, detail="Table not found")
    except asyncpg.UndefinedColumnError as e:
        raise HTTPException(status_code=400, detail=f"Unknown column: {e}")
    except asyncpg.PostgresError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── SELECT ─────────────────────────────────────────────────────────────────

@router.get("/{table}")
async def select_rows(
    table: str,
    request: Request,
    pool: DbDep,
    current_user: CurrentUser,
) -> JSONResponse:
    require_table_access(table)
    params = dict(request.query_params)
    sql, args = build_select_query(table, current_user["tenant_id"], params)
    rows = await _execute(pool, sql, args)
    return JSONResponse(content=_rows_to_json(rows))


# ── INSERT ────────────────────────────────────────────────────────────────

@router.post("/{table}", status_code=status.HTTP_201_CREATED)
async def insert_row(
    table: str,
    request: Request,
    pool: DbDep,
    current_user: CurrentUser,
) -> JSONResponse:
    require_table_access(table)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    sql, args = build_insert_query(table, current_user["tenant_id"], body)
    rows = await _execute(pool, sql, args)
    return JSONResponse(content=_rows_to_json(rows), status_code=status.HTTP_201_CREATED)


# ── UPDATE ────────────────────────────────────────────────────────────────

@router.patch("/{table}")
async def update_rows(
    table: str,
    request: Request,
    pool: DbDep,
    current_user: CurrentUser,
) -> JSONResponse:
    require_table_access(table)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON")

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    params = dict(request.query_params)
    sql, args = build_update_query(table, current_user["tenant_id"], body, params)
    rows = await _execute(pool, sql, args)
    return JSONResponse(content=_rows_to_json(rows))


# ── DELETE ────────────────────────────────────────────────────────────────

@router.delete("/{table}")
async def delete_rows(
    table: str,
    request: Request,
    pool: DbDep,
    current_user: CurrentUser,
) -> JSONResponse:
    require_table_access(table)
    params = dict(request.query_params)
    if not params:
        raise HTTPException(
            status_code=400,
            detail="DELETE requires at least one filter to prevent accidental full-table deletion",
        )
    sql, args = build_delete_query(table, current_user["tenant_id"], params)
    rows = await _execute(pool, sql, args)
    return JSONResponse(content=_rows_to_json(rows))
