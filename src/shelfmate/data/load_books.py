import logging

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger("shelfmate.data.load_books")


def load_books(path: str = "data/raw/books.csv") -> int:
    """Load the 10,000 books once. Returns how many rows were added (0 if the table already has rows)."""
    engine = create_engine(settings.database_url)
    if not inspect(engine).has_table("books"):
        raise RuntimeError(
            "The books table does not exist. Run `uv run alembic upgrade head` first."
        )
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM books")).scalar_one()
    if existing:
        log.warning(
            "books already holds %s rows, skipping the load",
            f"{existing:,}",
            extra={"rows": existing},
        )
        return 0

    raw = pd.read_csv(path)
    books = pd.DataFrame(
        {
            "id": raw["book_id"],
            "title": raw["title"],
            "author": raw["authors"],
            "year": raw["original_publication_year"].astype("Int64"),
        }
    )
    log.info(
        "Read %s books from %s",
        f"{len(books):,}",
        path,
        extra={"rows": len(books), "no_year": int(books["year"].isna().sum())},
    )
    # One transaction: if the load fails halfway, nothing is kept and it can be run again.
    with timed(log, "load books", rows=len(books)), engine.begin() as conn:
        books.to_sql("books", conn, if_exists="append", index=False)
        # The ids were given by hand, so move the id counter past them for future inserts.
        conn.execute(
            text(
                "SELECT setval(pg_get_serial_sequence('books', 'id'), (SELECT MAX(id) FROM books))"
            )
        )
    return len(books)


if __name__ == "__main__":
    setup_logging("loader")
    new_run("load-books")
    load_books()
