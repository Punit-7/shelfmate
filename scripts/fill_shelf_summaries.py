"""Makes summaries for the most-rated books that have none yet, fetching descriptions first."""

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.db.models import Book, Rating
from shelfmate.logging_setup import new_run, setup_logging
from shelfmate.recommender.summaries import get_summary

LIMIT = 5

if __name__ == "__main__":
    setup_logging("loader")
    new_run("fill-summaries")
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
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
            summary, source = get_summary(session, book)
            print(f"\n{book.id} {book.title}")
            print(f"  description: {len(book.description or '')} chars")
            print(f"  source: {source}")
            print(f"  summary: {summary}")
