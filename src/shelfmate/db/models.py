from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, ForeignKey, Index, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"
    # Declared here so Alembic knows the index exists and does not try to drop it.
    __table_args__ = (
        Index(
            "books_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str]
    year: Mapped[int | None]
    ol_work_id: Mapped[str | None]
    description: Mapped[str | None]
    cover_url: Mapped[str | None]
    series_name: Mapped[str | None]
    series_pos: Mapped[float | None]
    embedding = mapped_column(Vector(384), nullable=True)


class Edition(Base):
    __tablename__ = "editions"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    isbn13: Mapped[str] = mapped_column(String(13), unique=True)
    format: Mapped[str]  # "hardcover" or "paperback"


class Rating(Base):
    """One reader's rating of one book. A reader can rate a book only once."""

    __tablename__ = "ratings"

    # BigInteger matches the columns pandas created when the ratings were loaded.
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    book_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rating: Mapped[int] = mapped_column(BigInteger)


class ShelfEntry(Base):
    """One of your own books and the shelf it is on."""

    __tablename__ = "my_shelf"

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    shelf: Mapped[str]  # "read", "currently-reading" or "to-read"
    rating: Mapped[int] = mapped_column(default=0)  # 0 means not rated
    progress_pct: Mapped[int] = mapped_column(default=0)
    source: Mapped[str]  # where the entry came from, such as "agent" or "goodreads"
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]
