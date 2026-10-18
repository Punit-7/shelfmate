import logging
import time
import uuid
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.data.openlibrary import get_editions, search_book
from shelfmate.db.models import Book, Edition, ShelfEntry
from shelfmate.flows.pipeline import after_finished_book
from shelfmate.logging_setup import run_id, setup_logging

setup_logging("api")
log = logging.getLogger(__name__)
app = FastAPI(title="Shelfmate API")
engine = create_engine(settings.database_url)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    run_id.set(f"req-{rid}")
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        ms = round((time.perf_counter() - start) * 1000, 1)
        log.exception(
            "%s %s crashed after %.1f ms",
            request.method,
            request.url.path,
            ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": ms,
            },
        )
        raise
    ms = round((time.perf_counter() - start) * 1000, 1)
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    log.log(
        level,
        "%s %s -> %d in %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        ms,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": ms,
        },
    )
    response.headers["X-Request-ID"] = rid
    return response


class FinishRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


@app.get("/shelf")
def list_shelf(name: Literal["read", "currently-reading", "to-read"]):
    # ponytail: one ISBN per book (first by id), add a join if a book needs them all
    isbn13 = (
        select(Edition.isbn13)
        .where(Edition.book_id == ShelfEntry.book_id)
        .order_by(Edition.id)
        .limit(1)
        .scalar_subquery()
        .label("isbn13")
    )
    with Session(engine) as session:
        rows = session.execute(
            select(
                ShelfEntry.book_id,
                Book.title,
                Book.author,
                isbn13,
                ShelfEntry.rating,
                ShelfEntry.progress_pct,
            )
            .join(Book, Book.id == ShelfEntry.book_id)
            .where(ShelfEntry.shelf == name)
            .order_by(ShelfEntry.added_at.desc())
        ).mappings()
        return [dict(row) for row in rows]


def put_on_shelf(book_id: int, shelf: str, **fields) -> None:
    """Creates or updates a book's shelf entry. 404s if the book is unknown."""
    with Session(engine) as session:
        if session.get(Book, book_id) is None:
            raise HTTPException(status_code=404, detail=f"No book with id {book_id}")
        entry = session.get(ShelfEntry, book_id) or ShelfEntry(
            book_id=book_id, source="api"
        )
        entry.shelf = shelf
        for key, value in fields.items():
            setattr(entry, key, value)
        session.add(entry)
        session.commit()


def ensure_editions(book_id: int) -> None:
    """Fills the editions table from Open Library the first time a book is shelved."""
    with Session(engine) as session:
        if session.scalar(
            select(Edition.id).where(Edition.book_id == book_id).limit(1)
        ):
            return
        book = session.get(Book, book_id)
        title = book.title.split(" (")[0]  # drop the "(Series, #1)" suffix
        try:
            hit = search_book(title, book.author)
            editions = get_editions(hit["key"]) if hit else []
        except httpx.HTTPError:
            log.exception("Open Library lookup failed", extra={"book_id": book_id})
            return
        if editions:
            rows = [{"book_id": book_id, **e} for e in editions]
            session.execute(insert(Edition).values(rows).on_conflict_do_nothing())
            session.commit()


@app.post("/shelf/{book_id}/start")
def start_book(book_id: int, background: BackgroundTasks):
    put_on_shelf(book_id, "currently-reading", finished_at=None)
    background.add_task(ensure_editions, book_id)
    log.info("Book started", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id}


@app.post("/shelf/{book_id}/want")
def want_book(book_id: int, background: BackgroundTasks):
    put_on_shelf(book_id, "to-read", finished_at=None)
    background.add_task(ensure_editions, book_id)
    log.info("Book wanted", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id}


@app.post("/shelf/{book_id}/finish")
def finish_book(book_id: int, req: FinishRequest, background: BackgroundTasks):
    put_on_shelf(
        book_id,
        "read",
        rating=req.rating,
        progress_pct=100,
        finished_at=func.now(),
    )
    background.add_task(ensure_editions, book_id)
    log.info("Book finished", extra={"book_id": book_id, "rating": req.rating})
    background.add_task(after_finished_book)
    log.debug("Recommendation flow queued", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id, "rating": req.rating}
