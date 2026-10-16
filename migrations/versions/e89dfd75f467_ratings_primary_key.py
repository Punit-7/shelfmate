"""ratings primary key

Revision ID: e89dfd75f467
Revises: b49f842b8171
Create Date: 2026-10-16 08:17:10.324633

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e89dfd75f467"
down_revision: str | Sequence[str] | None = "b49f842b8171"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make `ratings` a proper table: NOT NULL columns and one row per reader and book.

    The table may not exist yet (a fresh database), or it may already exist because
    pandas created it when the ratings were loaded. This handles both.
    """
    if "ratings" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "ratings",
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("book_id", sa.BigInteger(), nullable=False),
            sa.Column("rating", sa.BigInteger(), nullable=False),
            sa.PrimaryKeyConstraint("user_id", "book_id", name="ratings_pkey"),
        )
        return

    # Keep one copy of any duplicated reader and book pair, so the key can be created.
    op.execute(
        "DELETE FROM ratings a USING ratings b "
        "WHERE a.ctid > b.ctid AND a.user_id = b.user_id AND a.book_id = b.book_id"
    )
    for column in ("user_id", "book_id", "rating"):
        op.alter_column(
            "ratings", column, existing_type=sa.BigInteger(), nullable=False
        )
    op.create_primary_key("ratings_pkey", "ratings", ["user_id", "book_id"])


def downgrade() -> None:
    """Remove the key and allow empty values again. The table stays, because it holds the data."""
    op.drop_constraint("ratings_pkey", "ratings", type_="primary")
    for column in ("user_id", "book_id", "rating"):
        op.alter_column("ratings", column, existing_type=sa.BigInteger(), nullable=True)
