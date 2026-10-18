import logging

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from shelfmate.db.models import Book, ShelfEntry

log = logging.getLogger(__name__)
SHELVES = {"read", "currently-reading", "to-read"}
COLUMNS = {"Title", "Author", "Exclusive Shelf", "My Rating", "Date Read"}


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def find_book(title: str, author: str, index: dict) -> int | None:
    """Matches a Goodreads row to a book id by title (with or without the series suffix) and author."""
    for key in (norm(title), norm(title.split(" (")[0])):
        for book_id, book_author in index.get(key, []):
            if author and norm(author) in book_author:
                return book_id
    return None


def import_goodreads(csv_file, engine) -> dict:
    """Adds books from a Goodreads export to my_shelf. Entries already on the shelf are kept.

    Raises ValueError if the file is not a CSV with the Goodreads export columns.
    """
    try:
        rows = pd.read_csv(csv_file, dtype=str).fillna("")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as e:
        raise ValueError(f"Not a readable CSV file: {e}") from e
    missing = COLUMNS - set(rows.columns)
    if missing:
        raise ValueError(
            f"Not a Goodreads export, missing: {', '.join(sorted(missing))}"
        )
    with Session(engine) as session:
        index: dict[str, list] = {}
        for book in session.execute(select(Book.id, Book.title, Book.author)):
            entry = (book.id, norm(book.author))
            for key in {norm(book.title), norm(book.title.split(" (")[0])}:
                index.setdefault(key, []).append(entry)
        seen = set(session.scalars(select(ShelfEntry.book_id)))

        imported, already, other_shelves, unmatched = 0, 0, 0, []
        for row in rows.to_dict("records"):
            shelf = row["Exclusive Shelf"]
            if shelf not in SHELVES:
                other_shelves += 1
                continue
            book_id = find_book(row["Title"], row["Author"], index)
            if book_id is None:
                unmatched.append(row["Title"])
            elif book_id in seen:
                already += 1
            else:
                finished = pd.to_datetime(row["Date Read"] or None, errors="coerce")
                session.add(
                    ShelfEntry(
                        book_id=book_id,
                        shelf=shelf,
                        rating=int(row["My Rating"] or 0),
                        source="goodreads",
                        finished_at=finished.to_pydatetime()
                        if pd.notna(finished)
                        else None,
                    )
                )
                seen.add(book_id)
                imported += 1
        session.commit()
    log.info(
        "Goodreads import done",
        extra={"imported": imported, "already": already, "unmatched": len(unmatched)},
    )
    return {
        "imported": imported,
        "already_on_shelf": already,
        "other_shelves": other_shelves,
        "unmatched": unmatched,
    }
