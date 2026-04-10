"""
query_builder.py
----------------
Parses Supabase-style URL filter parameters into safe, parameterised asyncpg SQL.

Supported filter operators (applied as query-string values):
  ?col=eq.value       → col = $N
  ?col=neq.value      → col != $N
  ?col=gt.value       → col > $N
  ?col=gte.value      → col >= $N
  ?col=lt.value       → col < $N
  ?col=lte.value      → col <= $N
  ?col=like.value     → col LIKE $N
  ?col=ilike.value    → col ILIKE $N
  ?col=is.null        → col IS NULL
  ?col=is.true        → col IS TRUE
  ?col=is.false       → col IS FALSE
  ?col=in.(a,b,c)     → col = ANY($N)

Other supported query params:
  select=col1,col2    → SELECT col1, col2 (default: *)
  order=col.asc|desc  → ORDER BY col ASC|DESC
  limit=N             → LIMIT N (max 1000)
  offset=N            → OFFSET N
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status

# Characters allowed in column / table names (prevent SQL injection)
_IDENT_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

_OPS = {
    "eq": "=",
    "neq": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "like": "LIKE",
    "ilike": "ILIKE",
}

_MAX_LIMIT = 1000
_DEFAULT_LIMIT = 100


def _validate_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid identifier: '{name}'",
        )
    return name


def _parse_select(select_param: str | None) -> str:
    """Return a safe SELECT column list."""
    if not select_param or select_param.strip() == "*":
        return "*"
    cols = [_validate_ident(c.strip()) for c in select_param.split(",") if c.strip()]
    if not cols:
        return "*"
    return ", ".join(f'"{c}"' for c in cols)


def _parse_order(order_param: str | None) -> str | None:
    """Return 'ORDER BY col ASC|DESC' or None."""
    if not order_param:
        return None
    parts = order_param.split(".")
    col = _validate_ident(parts[0])
    direction = "ASC"
    if len(parts) >= 2 and parts[1].lower() == "desc":
        direction = "DESC"
    return f'ORDER BY "{col}" {direction}'


def _parse_limit(limit_param: str | None, offset_param: str | None) -> tuple[int, int]:
    try:
        limit = min(int(limit_param), _MAX_LIMIT) if limit_param else _DEFAULT_LIMIT
    except ValueError:
        raise HTTPException(status_code=400, detail="'limit' must be an integer")
    try:
        offset = int(offset_param) if offset_param else 0
    except ValueError:
        raise HTTPException(status_code=400, detail="'offset' must be an integer")
    return limit, offset


def build_select_query(
    table: str,
    tenant_id: str,
    query_params: dict[str, str],
) -> tuple[str, list[Any]]:
    """
    Build a SELECT query for the given table scoped to tenant_id.
    Returns (sql, args) ready for asyncpg.
    """
    _validate_ident(table)

    select_cols = _parse_select(query_params.get("select"))
    order_clause = _parse_order(query_params.get("order"))
    limit, offset = _parse_limit(query_params.get("limit"), query_params.get("offset"))

    args: list[Any] = [tenant_id]
    param_idx = 2  # $1 is tenant_id

    where_parts = ['"tenant_id" = $1']

    # Reserved params that are not filters
    reserved = {"select", "order", "limit", "offset"}

    for key, raw_value in query_params.items():
        if key in reserved:
            continue
        col = _validate_ident(key)
        # Parse operator + value
        dot_idx = raw_value.find(".")
        if dot_idx == -1:
            raise HTTPException(
                status_code=400,
                detail=f"Filter '{key}' must use operator format: eq.value, gt.value, etc.",
            )
        op_str = raw_value[:dot_idx]
        val_str = raw_value[dot_idx + 1:]

        if op_str == "is":
            lower = val_str.lower()
            if lower == "null":
                where_parts.append(f'"{col}" IS NULL')
            elif lower == "true":
                where_parts.append(f'"{col}" IS TRUE')
            elif lower == "false":
                where_parts.append(f'"{col}" IS FALSE')
            else:
                raise HTTPException(status_code=400, detail="'is' operator only supports null/true/false")
            continue

        if op_str == "in":
            # val_str is like "(a,b,c)"
            inner = val_str.strip("()")
            values = [v.strip() for v in inner.split(",") if v.strip()]
            if not values:
                raise HTTPException(status_code=400, detail="'in' filter requires at least one value")
            args.append(values)
            where_parts.append(f'"{col}" = ANY(${param_idx})')
            param_idx += 1
            continue

        sql_op = _OPS.get(op_str)
        if not sql_op:
            raise HTTPException(status_code=400, detail=f"Unknown operator: '{op_str}'")

        args.append(val_str)
        where_parts.append(f'"{col}" {sql_op} ${param_idx}')
        param_idx += 1

    where_clause = " AND ".join(where_parts)
    sql = f'SELECT {select_cols} FROM "{table}" WHERE {where_clause}'
    if order_clause:
        sql += f" {order_clause}"
    sql += f" LIMIT {limit} OFFSET {offset}"

    return sql, args


def build_insert_query(
    table: str,
    tenant_id: str,
    data: dict[str, Any],
) -> tuple[str, list[Any]]:
    _validate_ident(table)
    # Force tenant_id
    data["tenant_id"] = tenant_id

    cols = [_validate_ident(k) for k in data.keys()]
    quoted_cols = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(cols)))
    args = list(data.values())

    sql = f'INSERT INTO "{table}" ({quoted_cols}) VALUES ({placeholders}) RETURNING *'
    return sql, args


def build_update_query(
    table: str,
    tenant_id: str,
    data: dict[str, Any],
    query_params: dict[str, str],
) -> tuple[str, list[Any]]:
    _validate_ident(table)
    # Remove tenant_id from update payload — can't change it
    data.pop("tenant_id", None)

    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")

    args: list[Any] = [tenant_id]
    param_idx = 2

    set_parts: list[str] = []
    for key, val in data.items():
        col = _validate_ident(key)
        args.append(val)
        set_parts.append(f'"{col}" = ${param_idx}')
        param_idx += 1

    set_clause = ", ".join(set_parts)
    where_parts = ['"tenant_id" = $1']
    reserved = {"select", "order", "limit", "offset"}

    for key, raw_value in query_params.items():
        if key in reserved:
            continue
        col = _validate_ident(key)
        dot_idx = raw_value.find(".")
        if dot_idx == -1:
            raise HTTPException(status_code=400, detail=f"Filter '{key}' must use operator format")
        op_str = raw_value[:dot_idx]
        val_str = raw_value[dot_idx + 1:]
        sql_op = _OPS.get(op_str)
        if not sql_op:
            raise HTTPException(status_code=400, detail=f"Unknown operator: '{op_str}'")
        args.append(val_str)
        where_parts.append(f'"{col}" {sql_op} ${param_idx}')
        param_idx += 1

    where_clause = " AND ".join(where_parts)
    sql = f'UPDATE "{table}" SET {set_clause} WHERE {where_clause} RETURNING *'
    return sql, args


def build_delete_query(
    table: str,
    tenant_id: str,
    query_params: dict[str, str],
) -> tuple[str, list[Any]]:
    _validate_ident(table)

    args: list[Any] = [tenant_id]
    param_idx = 2
    where_parts = ['"tenant_id" = $1']
    reserved = {"select", "order", "limit", "offset"}

    for key, raw_value in query_params.items():
        if key in reserved:
            continue
        col = _validate_ident(key)
        dot_idx = raw_value.find(".")
        if dot_idx == -1:
            raise HTTPException(status_code=400, detail=f"Filter '{key}' must use operator format")
        op_str = raw_value[:dot_idx]
        val_str = raw_value[dot_idx + 1:]
        sql_op = _OPS.get(op_str)
        if not sql_op:
            raise HTTPException(status_code=400, detail=f"Unknown operator: '{op_str}'")
        args.append(val_str)
        where_parts.append(f'"{col}" {sql_op} ${param_idx}')
        param_idx += 1

    where_clause = " AND ".join(where_parts)
    sql = f'DELETE FROM "{table}" WHERE {where_clause} RETURNING *'
    return sql, args
