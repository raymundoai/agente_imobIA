"""Rewrite machine-joined lead interests ("rent | comercial | São Paulo") as sentences.

Revision ID: 20261004_0028
Revises: 20261002_0027
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision = "20261004_0028"
down_revision = "20261002_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PURPOSES = {"buy": "Compra", "rent": "Aluguel"}


def _sentence(raw: str) -> str | None:
    parts = [part.strip() for part in raw.split("|") if part.strip()]
    if len(parts) < 2:
        return None
    action = PURPOSES.get(parts[0].lower())
    if action:
        parts = parts[1:]
    # The old summary always put the property type first and it was a lowercase code.
    kind = parts.pop(0).replace("_", " ").lower() if parts and parts[0].islower() else ""
    city = parts.pop(0) if parts else ""
    areas = ", ".join(parts)
    head = f"{action} de {kind or 'imóvel'}" if action else (kind[:1].upper() + kind[1:])
    if city:
        location = f"{city} ({areas})" if areas else city
        head = f"{head} em {location}" if head else location
    return head or None


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("SELECT id, interest FROM contacts WHERE interest LIKE '%|%'")
    ).all()
    for row in rows:
        sentence = _sentence(row.interest)
        if sentence:
            connection.execute(
                sa.text("UPDATE contacts SET interest = :interest WHERE id = :id"),
                {"interest": sentence, "id": row.id},
            )


def downgrade() -> None:
    # Text-only cleanup; the readable form is kept.
    pass
