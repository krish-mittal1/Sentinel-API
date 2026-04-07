"""Add auth lifecycle and admin support tables."""

from alembic import op
import sqlalchemy as sa


revision = "20260407_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    table_names = set(inspector.get_table_names())

    if "email_verified" not in user_columns:
        op.add_column(
            "users",
            sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.alter_column("users", "email_verified", server_default=None)

    if "last_login_at" not in user_columns:
        op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    if "refresh_sessions" not in table_names:
        op.create_table(
            "refresh_sessions",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("family_id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("parent_session_id", sa.UUID(), nullable=True),
            sa.Column("replaced_by_session_id", sa.UUID(), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_reason", sa.String(length=64), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["parent_session_id"], ["refresh_sessions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["replaced_by_session_id"], ["refresh_sessions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_refresh_sessions_family_id", "refresh_sessions", ["family_id"])
        op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
        op.create_index("ix_refresh_sessions_token_hash", "refresh_sessions", ["token_hash"])

    if "auth_tokens" not in table_names:
        op.create_table(
            "auth_tokens",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=False),
            sa.Column("token_type", sa.String(length=32), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])
        op.create_index("ix_auth_tokens_type", "auth_tokens", ["token_type"])
        op.create_index("ix_auth_tokens_token_hash", "auth_tokens", ["token_hash"])

    if "audit_logs" not in table_names:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.UUID(), nullable=True),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("user_agent", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
            sa.Column("details", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
        op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])
        op.create_index("ix_audit_logs_email", "audit_logs", ["email"])


def downgrade() -> None:
    op.drop_index("ix_audit_logs_email", table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_auth_tokens_token_hash", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_type", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")

    op.drop_index("ix_refresh_sessions_token_hash", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_user_id", table_name="refresh_sessions")
    op.drop_index("ix_refresh_sessions_family_id", table_name="refresh_sessions")
    op.drop_table("refresh_sessions")

    op.drop_column("users", "last_login_at")
    op.drop_column("users", "email_verified")
