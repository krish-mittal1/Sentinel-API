"""20260411_0003_data_service_support

Creates a demo `profiles` table and helper views for the Data API / Studio.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-11
"""

from alembic import op
import sqlalchemy as sa

# Alembic metadata
revision = "20260411_0003"
down_revision = "20260409_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Demo `profiles` table ────────────────────────────────────────────────
    # This is a user-facing table exposed via the Data API so developers can
    # immediately test SELECT/INSERT/UPDATE/DELETE without creating their own tables.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS profiles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            user_id     UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            display_name VARCHAR(100),
            bio         TEXT,
            avatar_url  VARCHAR(500),
            website     VARCHAR(500),
            metadata    JSONB DEFAULT '{}',
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_profiles_tenant_id ON profiles(tenant_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles(user_id);"
    )

    # Auto-update updated_at on profiles
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;
        CREATE TRIGGER trg_profiles_updated_at
            BEFORE UPDATE ON profiles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at();
        """
    )

    # ── pg_notify triggers for future Realtime support ───────────────────────
    # These fire NOTIFY on INSERT/UPDATE/DELETE on user-facing tables.
    # The Realtime service (Phase 2) will listen on these channels.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sentinel_notify_change()
        RETURNS TRIGGER AS $$
        DECLARE
            payload TEXT;
        BEGIN
            IF TG_OP = 'DELETE' THEN
                payload := json_build_object(
                    'table', TG_TABLE_NAME,
                    'type',  'DELETE',
                    'old',   row_to_json(OLD)
                )::text;
            ELSE
                payload := json_build_object(
                    'table', TG_TABLE_NAME,
                    'type',  TG_OP,
                    'new',   row_to_json(NEW)
                )::text;
            END IF;
            PERFORM pg_notify('sentinel_changes', payload);
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_profiles_notify ON profiles;
        CREATE TRIGGER trg_profiles_notify
            AFTER INSERT OR UPDATE OR DELETE ON profiles
            FOR EACH ROW EXECUTE FUNCTION sentinel_notify_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_notify ON profiles;")
    op.execute("DROP TRIGGER IF EXISTS trg_profiles_updated_at ON profiles;")
    op.execute("DROP TABLE IF EXISTS profiles;")
    op.execute("DROP FUNCTION IF EXISTS sentinel_notify_change();")
