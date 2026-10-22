import logging
import re
import time
import uuid
from typing import Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from shelfmate.agent.search import NEW_STORES, stocked_links
from shelfmate.config import settings
from shelfmate.data.import_goodreads import import_goodreads
from shelfmate.data.openlibrary import search_books
from shelfmate.db.models import Book, PipelineRun, Rating, Recommendation, ShelfEntry
from shelfmate.flows.pipeline import ensure_cover
from shelfmate.logging_setup import run_id, setup_logging

setup_logging("api")
log = logging.getLogger(__name__)
app = FastAPI(title="Shelfmate API")
engine = create_engine(settings.database_url, pool_pre_ping=True)


@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}


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
    chapter: int = Field(ge=0, le=10_000)
    total_chapters: int | None = Field(default=None, ge=1, le=10_000)

    @model_validator(mode="after")
    def chapter_within_book(self):
        if self.total_chapters is not None and self.chapter > self.total_chapters:
            raise ValueError("chapter cannot be more than total_chapters")
        return self


class AddBookRequest(BaseModel):
    """A book picked from the GET /search results."""

    ol_work_id: str = Field(pattern=r"^/works/OL\d+W$")
    title: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=500)
    year: int | None = None
    shelf: Literal["currently-reading", "to-read"]


@app.get("/shelf")
def list_shelf(
    name: Literal["read", "currently-reading", "to-read"], background: BackgroundTasks
):
    with Session(engine) as session:
        rows = session.execute(
            select(
                ShelfEntry.book_id,
                Book.title,
                Book.author,
                Book.cover_url,
                ShelfEntry.rating,
                ShelfEntry.chapter,
                ShelfEntry.total_chapters,
            )
            .join(Book, Book.id == ShelfEntry.book_id)
            .where(ShelfEntry.shelf == name)
            .order_by(ShelfEntry.added_at.desc())
        ).mappings()
        books = [dict(row) for row in rows]
    # A book with no cover lookup yet gets one now, and shows it on the next reload.
    for b in books:
        if b["cover_url"] is None:
            background.add_task(ensure_cover, b["book_id"])
    return books


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
    background.add_task(ensure_cover, book_id)
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
        entry.chapter, entry.total_chapters = req.chapter, req.total_chapters
        session.commit()
    return {"status": "saved", "book_id": book_id, **req.model_dump()}


@app.delete("/shelf/{book_id}")
def remove_book(book_id: int):
    """Takes a book off your shelves. The book stays in the catalogue."""
    with Session(engine) as session:
        entry = session.get(ShelfEntry, book_id)
        if entry is None:
            raise HTTPException(
                status_code=404, detail=f"Book {book_id} is not shelved"
            )
        session.delete(entry)
        session.commit()
    log.info("Book removed", extra={"book_id": book_id})
    return {"status": "removed", "book_id": book_id}


@app.post("/shelf/{book_id}/start")
def start_book(book_id: int, background: BackgroundTasks):
    put_on_shelf(book_id, "currently-reading", finished_at=None)
    background.add_task(ensure_cover, book_id)
    log.info("Book started", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id}


@app.post("/shelf/{book_id}/want")
def want_book(book_id: int, background: BackgroundTasks):
    put_on_shelf(book_id, "to-read", finished_at=None)
    background.add_task(ensure_cover, book_id)
    log.info("Book wanted", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id}


@app.post("/shelf/{book_id}/finish")
def finish_book(book_id: int, req: FinishRequest, background: BackgroundTasks):
    put_on_shelf(
        book_id,
        "read",
        rating=req.rating,
        finished_at=func.now(),
    )
    background.add_task(ensure_cover, book_id)
    log.info("Book finished", extra={"book_id": book_id, "rating": req.rating})
    # The worker runs the flow. The row is there before this returns, so the website
    # sees the run as busy on its very next look.
    with Session(engine) as session, session.begin():
        session.add(PipelineRun())
    log.debug("Recommendation run requested", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id, "rating": req.rating}


def pipeline_busy() -> str | None:
    """What the worker is doing for the website: "recommendations", "summaries" or None."""
    with Session(engine) as session:
        states = set(
            session.scalars(
                select(PipelineRun.status).where(
                    PipelineRun.status.in_(["queued", "running", "summaries"])
                )
            )
        )
    if states & {"queued", "running"}:
        return "recommendations"
    return "summaries" if states else None


def page_lanes(books: list[dict], offset: int, limit: int, lane: str | None):
    """Splits ranked books into their lanes and cuts one page out of each.

    lane limits the page to one lane. total is how many books each lane holds, so the
    website knows when there is nothing more to show.
    """
    lanes: dict[str, list] = {"continue": [], "new": []}
    for b in books:
        lanes[b["lane"]].append(b)
    total = {name: len(items) for name, items in lanes.items()}
    page = {
        name: items[offset : offset + limit] if lane in (None, name) else []
        for name, items in lanes.items()
    }
    return page, total


@app.get("/recommendations")
def list_recommendations(
    background: BackgroundTasks,
    offset: int = Query(0, ge=0),
    limit: int = Query(5, ge=1, le=20),
    lane: Literal["continue", "new"] | None = None,
):
    """Both lanes from the last pipeline run, with summaries, reasons and store links.

    Each lane returns one page of `limit` books starting at `offset`. Ask for the next
    page with offset=5, and `total` says when a lane has no more.
    """
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
                    Book.cover_url,
                )
                .join(Book, Book.id == Recommendation.book_id)
                .order_by(Recommendation.rank)
            ).mappings()
        ]
    page, total = page_lanes(books, offset, limit, lane)
    # Store links are looked up for this page only, so a page takes about as long as one search.
    shown = [b for items in page.values() for b in items]
    shops = stocked_links([(b["title"], b["author"]) for b in shown], NEW_STORES)
    for b, links in zip(shown, shops):
        if b["cover_url"] is None:
            background.add_task(ensure_cover, b["book_id"])
        b["shops"] = links
        del b["lane"]
    # busy tells the website to look again: new picks coming, or summaries being written.
    return {**page, "total": total, "busy": pipeline_busy()}


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


@app.get("/stats")
def stats():
    """Counts for the dashboard: books per shelf, your ratings, the catalogue size and your last five finished books."""
    with Session(engine) as session:
        shelves = dict(
            session.execute(
                select(ShelfEntry.shelf, func.count()).group_by(ShelfEntry.shelf)
            ).all()
        )
        ratings = dict(
            session.execute(
                select(ShelfEntry.rating, func.count())
                .where(ShelfEntry.shelf == "read", ShelfEntry.rating > 0)
                .group_by(ShelfEntry.rating)
            ).all()
        )
        catalogue = session.scalar(select(func.count()).select_from(Book))
        recent = [
            dict(row)
            for row in session.execute(
                select(
                    Book.id.label("book_id"),
                    Book.title,
                    Book.cover_url,
                    ShelfEntry.rating,
                )
                .join(Book, Book.id == ShelfEntry.book_id)
                .where(ShelfEntry.shelf == "read")
                .order_by(ShelfEntry.finished_at.desc())
                .limit(5)
            ).mappings()
        ]
        # One query for all five books, so the ratings table is read once.
        community = dict(
            session.execute(
                select(Rating.book_id, func.avg(Rating.rating))
                .where(Rating.book_id.in_([b["book_id"] for b in recent]))
                .group_by(Rating.book_id)
            ).all()
        )
    for b in recent:
        avg = community.get(b["book_id"])
        b["community"] = round(float(avg), 2) if avg is not None else None
    return {
        "shelves": shelves,
        "ratings": ratings,
        "catalogue": catalogue,
        "recent": recent,
    }
