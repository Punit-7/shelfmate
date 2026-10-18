"""add summary columns to books

Revision ID: 146bbf582577
Revises: f23d769b7d9e
Create Date: 2026-10-18 17:06:35.920153

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "146bbf582577"
down_revision: str | Sequence[str] | None = "f23d769b7d9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("books", sa.Column("summary", sa.String(), nullable=True))
    op.add_column("books", sa.Column("summary_source", sa.String(), nullable=True))
    op.add_column("books", sa.Column("summary_model", sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("books", "summary_model")
    op.drop_column("books", "summary_source")
    op.drop_column("books", "summary")
