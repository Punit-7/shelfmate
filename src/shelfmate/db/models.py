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
    summary: Mapped[str | None]
    summary_source: Mapped[str | None]  # "llm", "description" or "none"
    summary_model: Mapped[str | None]
    genres: Mapped[str | None]  # "science-fiction, dystopian", from the goodbooks tags
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
    chapter: Mapped[int] = mapped_column(default=0)  # the chapter you are on
    total_chapters: Mapped[int | None]  # None until you enter it
    source: Mapped[str]  # where the entry came from, such as "agent" or "goodreads"
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
    finished_at: Mapped[datetime | None]


class Price(Base):
    """The cheapest offer found for one book, store, format and condition."""

    __tablename__ = "prices"

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    store: Mapped[str] = mapped_column(primary_key=True)
    format: Mapped[str] = mapped_column(primary_key=True)
    condition: Mapped[str] = mapped_column(primary_key=True)
    price_inr: Mapped[float]
    url: Mapped[str]
    checked_at: Mapped[datetime]


class Recommendation(Base):
    """One book on the Recommendations shelf. The pipeline replaces all rows each run."""

    __tablename__ = "recommendations"

    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    lane: Mapped[str]  # "continue" or "new"
    rank: Mapped[int]
    because: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class PipelineRun(Base):
    """A request to rebuild the recommendations. The API adds one, the worker runs it."""

    __tablename__ = "pipeline_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # queued, running, summaries (picks saved, writing summaries), done or failed
    status: Mapped[str] = mapped_column(default="queued")
    requested_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
