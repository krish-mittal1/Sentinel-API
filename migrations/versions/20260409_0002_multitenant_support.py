"""Add tenant isolation across auth and user data."""

from alembic import op
import sqlalchemy as sa


revision = "20260409_0002"
down_revision = "20260407_0001"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def _has_fk(inspector, table_name: str, fk_name: str) -> bool:
    return fk_name in {fk["name"] for fk in inspector.get_foreign_keys(table_name)}


def _has_unique(inspector, table_name: str, constraint_name: str) -> bool:
    return constraint_name in {uq["name"] for uq in inspector.get_unique_constraints(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "tenants"):
        op.create_table(
            "tenants",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("slug", sa.String(length=64), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("slug"),
        )
        op.create_index("ix_tenants_slug", "tenants", ["slug"])

    bind.execute(
        sa.text(
            """
            INSERT INTO tenants (id, name, slug, is_active, created_at, updated_at)
            SELECT gen_random_uuid(), 'Default Tenant', 'default', TRUE, NOW(), NOW()
            WHERE NOT EXISTS (SELECT 1 FROM tenants WHERE slug = 'default')
            """
        )
    )
    default_tenant_id = bind.execute(
        sa.text("SELECT id FROM tenants WHERE slug = 'default' LIMIT 1")
    ).scalar_one()

    for table_name in ("users", "refresh_sessions", "auth_tokens", "audit_logs"):
        if not _has_column(inspector, table_name, "tenant_id"):
            op.add_column(table_name, sa.Column("tenant_id", sa.UUID(), nullable=True))
            bind.execute(sa.text(f"UPDATE {table_name} SET tenant_id = :tenant_id WHERE tenant_id IS NULL"), {"tenant_id": default_tenant_id})
            op.alter_column(table_name, "tenant_id", nullable=False)

    inspector = sa.inspect(bind)

    fk_specs = [
        ("users", "fk_users_tenant_id", "tenants", ["tenant_id"], ["id"]),
        ("refresh_sessions", "fk_refresh_sessions_tenant_id", "tenants", ["tenant_id"], ["id"]),
        ("auth_tokens", "fk_auth_tokens_tenant_id", "tenants", ["tenant_id"], ["id"]),
        ("audit_logs", "fk_audit_logs_tenant_id", "tenants", ["tenant_id"], ["id"]),
    ]
    for table_name, fk_name, ref_table, local_cols, remote_cols in fk_specs:
        if not _has_fk(inspector, table_name, fk_name):
            op.create_foreign_key(fk_name, table_name, ref_table, local_cols, remote_cols, ondelete="CASCADE")

    index_specs = [
        ("users", "ix_users_tenant_id", ["tenant_id"]),
        ("refresh_sessions", "ix_refresh_sessions_tenant_id", ["tenant_id"]),
        ("auth_tokens", "ix_auth_tokens_tenant_id", ["tenant_id"]),
        ("audit_logs", "ix_audit_logs_tenant_id", ["tenant_id"]),
    ]
    for table_name, index_name, columns in index_specs:
        if not _has_index(inspector, table_name, index_name):
            op.create_index(index_name, table_name, columns)

    if _has_unique(inspector, "users", "users_email_key"):
        op.drop_constraint("users_email_key", "users", type_="unique")
    inspector = sa.inspect(bind)
    if not _has_unique(inspector, "users", "uq_users_tenant_email"):
        op.create_unique_constraint("uq_users_tenant_email", "users", ["tenant_id", "email"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_unique(inspector, "users", "uq_users_tenant_email"):
        op.drop_constraint("uq_users_tenant_email", "users", type_="unique")
    if not _has_unique(inspector, "users", "users_email_key"):
        op.create_unique_constraint("users_email_key", "users", ["email"])

    for table_name, index_name in [
        ("audit_logs", "ix_audit_logs_tenant_id"),
        ("auth_tokens", "ix_auth_tokens_tenant_id"),
        ("refresh_sessions", "ix_refresh_sessions_tenant_id"),
        ("users", "ix_users_tenant_id"),
    ]:
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name, fk_name in [
        ("audit_logs", "fk_audit_logs_tenant_id"),
        ("auth_tokens", "fk_auth_tokens_tenant_id"),
        ("refresh_sessions", "fk_refresh_sessions_tenant_id"),
        ("users", "fk_users_tenant_id"),
    ]:
        if _has_fk(inspector, table_name, fk_name):
            op.drop_constraint(fk_name, table_name, type_="foreignkey")

    for table_name in ("audit_logs", "auth_tokens", "refresh_sessions", "users"):
        if _has_column(inspector, table_name, "tenant_id"):
            op.drop_column(table_name, "tenant_id")

    if _has_table(inspector, "tenants"):
        if _has_index(inspector, "tenants", "ix_tenants_slug"):
            op.drop_index("ix_tenants_slug", table_name="tenants")
        op.drop_table("tenants")
