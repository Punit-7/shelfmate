from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str]
    year: Mapped[int | None]
    ol_work_id: Mapped[str | None]
    description: Mapped[str | None]
    cover_url: Mapped[str | None]
    embedding = mapped_column(Vector(384), nullable=True)


class Edition(Base):
    __tablename__ = "editions"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    isbn13: Mapped[str] = mapped_column(String(13), unique=True)
    format: Mapped[str]  # "hardcover" or "paperback"
