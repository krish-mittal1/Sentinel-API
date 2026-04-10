"""
schema_inspector.py
-------------------
Introspects pg_catalog to return table and column metadata.
Used by the Studio Table Editor and API Docs views.
"""

from __future__ import annotations

import asyncpg

from .dependencies import BLOCKED_TABLES


async def list_user_tables(pool: asyncpg.Pool) -> list[dict]:
    """
    Return all non-internal tables that have a tenant_id column,
    excluding Sentinel internals.
    """
    rows = await pool.fetch(
        """
        SELECT
            t.table_name,
            (
                SELECT COUNT(*)
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name = t.table_name
            ) AS column_count
        FROM information_schema.tables t
        WHERE t.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
          AND t.table_name NOT IN (
            SELECT unnest($1::text[])
          )
          AND EXISTS (
            SELECT 1
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
              AND c.table_name = t.table_name
              AND c.column_name = 'tenant_id'
          )
        ORDER BY t.table_name
        """,
        list(BLOCKED_TABLES),
    )
    return [dict(r) for r in rows]


async def describe_table(pool: asyncpg.Pool, table: str) -> list[dict]:
    """
    Return column metadata for a specific table.
    """
    rows = await pool.fetch(
        """
        SELECT
            column_name,
            data_type,
            is_nullable,
            column_default,
            character_maximum_length,
            ordinal_position
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = $1
        ORDER BY ordinal_position
        """,
        table,
    )
    return [dict(r) for r in rows]


async def get_full_schema(pool: asyncpg.Pool) -> list[dict]:
    """
    Return all user tables with their columns embedded.
    Used by the Studio schema view and SDK auto-complete.
    """
    tables = await list_user_tables(pool)
    result = []
    for t in tables:
        columns = await describe_table(pool, t["table_name"])
        result.append(
            {
                "table": t["table_name"],
                "column_count": t["column_count"],
                "columns": columns,
            }
        )
    return result
