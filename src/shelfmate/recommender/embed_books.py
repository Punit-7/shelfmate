import logging

from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.db.models import Book
from shelfmate.logging_setup import new_run, setup_logging, timed
from shelfmate.recommender.content import embed

log = logging.getLogger("shelfmate.recommender.embed_books")
BATCH = 500


def embed_books() -> int:
    """Store an embedding for every book that has none yet. Safe to run again.

    The text is the title and the author. Descriptions from Open Library are not
    loaded yet; when they are, add them to the text and clear `books.embedding`.
    """
    engine = create_engine(settings.database_url)
    with Session(engine) as session:
        todo = session.execute(
            select(Book.id, Book.title, Book.author)
            .where(Book.embedding.is_(None))
            .order_by(Book.id)
        ).all()
    log.info("Books without an embedding", extra={"rows": len(todo)})

    done = 0
    for start in range(0, len(todo), BATCH):
        chunk = todo[start : start + BATCH]
        vectors = embed([f"{title}. {author}" for _, title, author in chunk])
        rows = [
            {"id": book_id, "embedding": vector.tolist()}
            for (book_id, _, _), vector in zip(chunk, vectors, strict=True)
        ]
        # One transaction per batch: a failure loses at most one batch.
        with Session(engine) as session, session.begin():
            session.execute(update(Book), rows)
        done += len(chunk)
        log.info("Embedded %d of %d", done, len(todo), extra={"done": done})
    return done


if __name__ == "__main__":
    setup_logging("recommender")
    new_run("embed-books")
    with timed(log, "embed books"):
        embed_books()
