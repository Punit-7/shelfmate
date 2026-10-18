"""Fetches Open Library descriptions for books on my_shelf, then makes their summaries."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.data.openlibrary import get_description, search_book
from shelfmate.db.models import Book, ShelfEntry
from shelfmate.logging_setup import new_run, setup_logging
from shelfmate.recommender.summaries import get_summary

LIMIT = 5

if __name__ == "__main__":
    setup_logging("loader")
    new_run("fill-summaries")
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        ids = session.scalars(
            select(ShelfEntry.book_id).order_by(ShelfEntry.added_at).limit(LIMIT)
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
