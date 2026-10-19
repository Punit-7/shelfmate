"""add genres to books

Revision ID: 7ece5aafbea6
Revises: 3c65cbee450f
Create Date: 2026-10-19 13:05:28.288256

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ece5aafbea6"
down_revision: str | Sequence[str] | None = "3c65cbee450f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("books", sa.Column("genres", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("books", "genres")
