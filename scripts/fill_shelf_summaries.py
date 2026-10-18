"""Fetches Open Library descriptions for the most-rated books, then makes their summaries."""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.data.openlibrary import get_description, search_book
from shelfmate.db.models import Book, Rating
from shelfmate.logging_setup import new_run, setup_logging
from shelfmate.recommender.summaries import get_summary

LIMIT = 5

if __name__ == "__main__":
    setup_logging("loader")
    new_run("fill-summaries")
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        # The five most-rated books that have no summary yet.
        ids = session.scalars(
            select(Rating.book_id)
            .join(Book, Book.id == Rating.book_id)
            .where(Book.summary.is_(None))
            .group_by(Rating.book_id)
            .order_by(func.count().desc())
            .limit(LIMIT)
        ).all()
        for book_id in ids:
            book = session.get(Book, book_id)
            if book.description is None:
                hit = search_book(book.title.split(" (")[0], book.author)
                if hit:
                    book.ol_work_id = hit["key"]
                    book.description = get_description(hit["key"])
                session.commit()
            print(f"\n{book.id} {book.title}")
            print(f"  description: {len(book.description or '')} chars")
            if book.description:
                summary, source = get_summary(session, book)
                print(f"  source: {source}")
                print(f"  summary: {summary}")
