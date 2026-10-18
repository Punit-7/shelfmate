import logging
import re
import time
import uuid
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from shelfmate.config import settings
from shelfmate.data.import_goodreads import import_goodreads
from shelfmate.data.openlibrary import search_books
from shelfmate.db.models import Book, Edition, Price, Recommendation, ShelfEntry
from shelfmate.flows.pipeline import after_finished_book, ensure_editions
from shelfmate.logging_setup import run_id, setup_logging

setup_logging("api")
log = logging.getLogger(__name__)
app = FastAPI(title="Shelfmate API")
engine = create_engine(settings.database_url)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    # The header comes from the client, so keep only safe characters before logging it.
    rid = re.sub(r"[^A-Za-z0-9-]", "", request.headers.get("X-Request-ID", ""))[:32]
    rid = rid or uuid.uuid4().hex[:8]
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


class ProgressRequest(BaseModel):
    progress_pct: int = Field(ge=0, le=100)


class AddBookRequest(BaseModel):
    """A book picked from the GET /search results."""

    ol_work_id: str = Field(pattern=r"^/works/OL\d+W$")
    title: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=500)
    year: int | None = None
    shelf: Literal["currently-reading", "to-read"]


def first_isbn(book_id):
    """The book's first saved ISBN, used for its cover image."""
    # ponytail: one ISBN per book (first by id), add a join if a book needs them all
    return (
        select(Edition.isbn13)
        .where(Edition.book_id == book_id)
        .order_by(Edition.id)
        .limit(1)
        .scalar_subquery()
        .label("isbn13")
    )


@app.get("/shelf")
def list_shelf(name: Literal["read", "currently-reading", "to-read"]):
    with Session(engine) as session:
        rows = session.execute(
            select(
                ShelfEntry.book_id,
                Book.title,
                Book.author,
                first_isbn(ShelfEntry.book_id),
                ShelfEntry.rating,
                ShelfEntry.progress_pct,
            )
            .join(Book, Book.id == ShelfEntry.book_id)
            .where(ShelfEntry.shelf == name)
            .order_by(ShelfEntry.added_at.desc())
        ).mappings()
        return [dict(row) for row in rows]


def put_on_shelf(book_id: int, shelf: str, source: str = "api", **fields) -> None:
    """Creates or updates a book's shelf entry. 404s if the book is unknown."""
    with Session(engine) as session:
        if session.get(Book, book_id) is None:
            raise HTTPException(status_code=404, detail=f"No book with id {book_id}")
        entry = session.get(ShelfEntry, book_id) or ShelfEntry(
            book_id=book_id, source=source
        )
        entry.shelf = shelf
        for key, value in fields.items():
            setattr(entry, key, value)
        session.add(entry)
        session.commit()


def embed_new_books() -> None:
    # Imported here, so the embedding model loads only when a new book needs it.
    from shelfmate.recommender.embed_books import embed_books

    embed_books()


@app.post("/shelf")
def add_book(req: AddBookRequest, background: BackgroundTasks):
    """Adds a book picked from Open Library, creating it in the catalogue if needed."""
    with Session(engine) as session:
        first_author = req.author.split(",")[0].strip()
        book = session.scalar(
            select(Book).where(Book.ol_work_id == req.ol_work_id)
        ) or session.scalar(
            # A catalogue book with the same title and author, not yet linked.
            select(Book)
            .where(
                func.lower(func.split_part(Book.title, " (", 1)) == req.title.lower(),
                Book.author.icontains(first_author, autoescape=True),
            )
            .limit(1)
        )
        if book is None:
            book = Book(
                title=req.title,
                author=req.author,
                year=req.year,
                ol_work_id=req.ol_work_id,
            )
            session.add(book)
            session.commit()
            background.add_task(embed_new_books)
        book_id = book.id
    put_on_shelf(book_id, req.shelf, source="manual", finished_at=None)
    background.add_task(ensure_editions, book_id)
    log.info("Book added", extra={"book_id": book_id, "shelf": req.shelf})
    return {"status": "saved", "book_id": book_id}


@app.patch("/shelf/{book_id}/progress")
def update_progress(book_id: int, req: ProgressRequest):
    with Session(engine) as session:
        entry = session.get(ShelfEntry, book_id)
        if entry is None:
            raise HTTPException(
                status_code=404, detail=f"Book {book_id} is not shelved"
            )
        entry.progress_pct = req.progress_pct
        session.commit()
    return {"status": "saved", "book_id": book_id, "progress_pct": req.progress_pct}


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


@app.get("/recommendations")
def list_recommendations():
    """Both lanes from the last pipeline run, with summaries, reasons and saved prices."""
    with Session(engine) as session:
        books = [
            dict(row)
            for row in session.execute(
                select(
                    Recommendation.book_id,
                    Recommendation.lane,
                    Recommendation.because,
                    Book.title,
                    Book.author,
                    Book.summary,
                    Book.summary_source,
                    first_isbn(Recommendation.book_id),
                )
                .join(Book, Book.id == Recommendation.book_id)
                .order_by(Recommendation.rank)
            ).mappings()
        ]
        offers: dict[int, list] = {}
        for p in session.scalars(
            select(Price)
            .where(Price.book_id.in_([b["book_id"] for b in books]))
            .order_by(Price.price_inr)
        ):
            offers.setdefault(p.book_id, []).append(
                {
                    "store": p.store,
                    "format": p.format,
                    "condition": p.condition,
                    "price_inr": p.price_inr,
                    "url": p.url,
                    "checked_at": p.checked_at,
                }
            )
    lanes: dict[str, list] = {"continue": [], "new": []}
    for b in books:
        lanes[b.pop("lane")].append({**b, "offers": offers.get(b["book_id"], [])})
    return lanes


@app.get("/search")
def search(q: str = Query(min_length=2, max_length=200)):
    """Searches Open Library, to add a book that is not in the catalogue."""
    try:
        return search_books(q)
    except httpx.HTTPError as e:
        log.warning("Open Library search failed", extra={"error": str(e)})
        raise HTTPException(
            status_code=502, detail="Open Library is not answering"
        ) from e


@app.post("/import/goodreads")
def import_goodreads_export(file: UploadFile):
    try:
        return import_goodreads(file.file, engine)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
