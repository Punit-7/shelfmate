"""add hnsw index on book embeddings

Revision ID: b49f842b8171
Revises: fa8073639a8a
Create Date: 2026-10-16 07:16:17.612770

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b49f842b8171"
down_revision: Union[str, Sequence[str], None] = "fa8073639a8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "CREATE INDEX books_embedding_hnsw ON books "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX books_embedding_hnsw")
