"""Allow Telegram conversations and messages.

Revision ID: 20260712_0010
Revises: 20260712_0009
"""

from alembic import op

revision = "20260712_0010"
down_revision = "20260712_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("conversations", "messages"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_channel")
        op.create_check_constraint(
            op.f(f"ck_{table}_channel"),
            table,
            "channel IN ('whatsapp', 'telegram')",
        )


def downgrade() -> None:
    for table in ("conversations", "messages"):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS ck_{table}_channel")
        op.create_check_constraint(op.f(f"ck_{table}_channel"), table, "channel IN ('whatsapp')")
