import logging
import re
import threading
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date
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
from shelfmate.db.models import (
    Book,
    DismissedBook,
    PipelineRun,
    Rating,
    Recommendation,
    ShelfEntry,
)
from shelfmate.flows.pipeline import ensure_cover
from shelfmate.logging_setup import run_id, setup_logging

setup_logging("api")
log = logging.getLogger(__name__)


def warm_store_links(top: int = 25) -> None:
    """Checks the stores for the best recommendations, so the first page opens fast.

    The checks are remembered for a day, but only in this process, so a restart forgets them.
    """
    try:
        with Session(engine) as session:
            rows = session.execute(
                select(Book.title, Book.author)
                .join(Recommendation, Recommendation.book_id == Book.id)
                .order_by(Recommendation.rank)
                .limit(top)
            ).all()
        stocked_links([(t, a) for t, a in rows], NEW_STORES)
        log.info("Store links warmed", extra={"books": len(rows)})
    except Exception:
        log.warning("Could not warm the store links", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    threading.Thread(target=warm_store_links, name="warm-links", daemon=True).start()
    yield


app = FastAPI(title="Shelfmate API", lifespan=lifespan)
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


# The recommender learns from these two shelves. A book moving in or out of them changes your
# recommendations, so the worker is asked to rebuild them.
TASTE_SHELVES = {"read", "currently-reading"}


def put_on_shelf(book_id: int, shelf: str, source: str = "api", **fields) -> None:
    """Creates or updates a book's shelf entry. 404s if the book is unknown."""
    with Session(engine) as session:
        if session.get(Book, book_id) is None:
            raise HTTPException(status_code=404, detail=f"No book with id {book_id}")
        entry = session.get(ShelfEntry, book_id) or ShelfEntry(
            book_id=book_id, source=source
        )
        before = entry.shelf
        entry.shelf = shelf
        for key, value in fields.items():
            setattr(entry, key, value)
        session.add(entry)
        if before != shelf and {before, shelf} & TASTE_SHELVES:
            session.add(PipelineRun())
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
        if entry.shelf in TASTE_SHELVES:
            session.add(PipelineRun())
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


@app.patch("/shelf/{book_id}/rating")
def update_rating(book_id: int, req: FinishRequest):
    """Changes the rating of a book you have finished. The recommendations are rebuilt."""
    with Session(engine) as session, session.begin():
        entry = session.get(ShelfEntry, book_id)
        if entry is None or entry.shelf != "read":
            raise HTTPException(
                status_code=404, detail=f"Book {book_id} is not on your read shelf"
            )
        entry.rating = req.rating
        session.add(PipelineRun())  # your taste changed, so ask the worker to rebuild
    log.info("Rating changed", extra={"book_id": book_id, "rating": req.rating})
    return {"status": "saved", "book_id": book_id, "rating": req.rating}


class AskRequest(BaseModel):
    message: str = Field(min_length=2, max_length=500)


# The local model answers one question at a time. A second question waits for a 429, not a queue.
chat_lock = threading.Lock()


ask_jobs: dict[str, dict] = {}  # job id -> {"status": ..., and the answer once done}


def run_ask(job_id: str, message: str) -> None:
    """Answers one question in the background. The website polls for the result."""
    from shelfmate.agent.graph import ask, strip_unlisted_links, tools_called

    try:
        result = ask(message)
        tools = tools_called(result)
        answer = strip_unlisted_links(result["messages"][-1].content, result)
        if "log_finished_book" in tools:
            # The agent saved a finished book itself, so the recommendations need rebuilding too.
            with Session(engine) as session, session.begin():
                session.add(PipelineRun())
        ask_jobs[job_id] = {"status": "done", "answer": answer, "tools": tools}
    except Exception:
        log.exception("Agent failed")
        ask_jobs[job_id] = {
            "status": "failed",
            "detail": "The assistant could not answer. Try again.",
        }
    finally:
        chat_lock.release()


@app.post("/agent/ask", status_code=202)
def agent_ask(req: AskRequest):
    """Starts an answer and returns a job id at once. Ask GET /agent/ask/{id} until it is done.

    A long answer on a CPU-only PC takes minutes, and a single request that long is dropped
    by the proxy in front of the API. Polling keeps every request short.
    """
    if not chat_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Shelfmate is answering another question. Try again in a minute.",
        )
    job_id = uuid.uuid4().hex
    ask_jobs[job_id] = {"status": "running"}
    threading.Thread(target=run_ask, args=(job_id, req.message), daemon=True).start()
    return {"job": job_id}


@app.get("/agent/ask/{job_id}")
def agent_ask_result(job_id: str):
    """The answer once it is ready. Until then the status is "running"."""
    job = ask_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such question")
    if job["status"] != "running":
        ask_jobs.pop(job_id, None)  # the answer is handed over once
    return job


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


def split_genres(text: str | None) -> list[str]:
    """The genres of one book, from the comma-separated text saved with it."""
    return [g.strip().lower() for g in (text or "").split(",") if g.strip()]


def common_genres(books: list[dict], top: int = 12) -> list[str]:
    """The genres found in these books, the most common first."""
    counts = Counter(g for b in books for g in set(split_genres(b["genres"])))
    return [g for g, _ in sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:top]]


def fill_months(counts: dict[str, int], today: date, n: int = 12) -> list[dict]:
    """The last n months, oldest first, with 0 for a month with no finished books."""
    months, y, m = [], today.year, today.month
    for _ in range(n):
        months.append(f"{y}-{m:02d}")
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return [{"month": k, "count": counts.get(k, 0)} for k in reversed(months)]


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
    genre: str | None = Query(None, max_length=60),
):
    """Both lanes from the last pipeline run, with summaries, reasons and store links.

    Each lane returns one page of `limit` books starting at `offset`. Ask for the next
    page with offset=5, and `total` says when a lane has no more. genre keeps only the
    books of that genre, and genres lists the choices. Books marked "not interested" are left out.
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
                    Book.genres,
                )
                .join(Book, Book.id == Recommendation.book_id)
                .where(Recommendation.book_id.not_in(select(DismissedBook.book_id)))
                # A book you just put on a shelf disappears at once, before the rebuild.
                .where(Recommendation.book_id.not_in(select(ShelfEntry.book_id)))
                .order_by(Recommendation.rank)
            ).mappings()
        ]
    genres = common_genres(books)
    if genre:
        books = [b for b in books if genre.lower() in split_genres(b["genres"])]
    page, total = page_lanes(books, offset, limit, lane)
    # Store links are looked up for this page only, so a page takes about as long as one search.
    shown = [b for items in page.values() for b in items]
    # The next page is checked in the background, so Show more opens at once.
    ahead, _ = page_lanes(books, offset + limit, limit, lane)
    upcoming = [(b["title"], b["author"]) for items in ahead.values() for b in items]
    if upcoming:
        background.add_task(stocked_links, upcoming, NEW_STORES)
    shops = stocked_links([(b["title"], b["author"]) for b in shown], NEW_STORES)
    for b, links in zip(shown, shops):
        if b["cover_url"] is None:
            background.add_task(ensure_cover, b["book_id"])
        b["shops"] = links
        del b["lane"], b["genres"]
    # busy tells the website to look again: new picks coming, or summaries being written.
    return {**page, "total": total, "genres": genres, "busy": pipeline_busy()}


@app.post("/recommendations/{book_id}/dismiss")
def dismiss_book(book_id: int):
    """Marks a book "not interested": it is hidden now and never recommended again."""
    with Session(engine) as session, session.begin():
        if session.get(Book, book_id) is None:
            raise HTTPException(status_code=404, detail=f"No book with id {book_id}")
        if session.get(DismissedBook, book_id) is None:
            session.add(DismissedBook(book_id=book_id))
    log.info("Book dismissed", extra={"book_id": book_id})
    return {"status": "dismissed", "book_id": book_id}


@app.delete("/recommendations/{book_id}/dismiss")
def undo_dismiss(book_id: int):
    """Takes the book off the not-interested list, so it can show up again."""
    with Session(engine) as session, session.begin():
        entry = session.get(DismissedBook, book_id)
        if entry is not None:
            session.delete(entry)
    log.info("Book restored", extra={"book_id": book_id})
    return {"status": "restored", "book_id": book_id}


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
        month = func.to_char(ShelfEntry.finished_at, "YYYY-MM")
        by_month = dict(
            session.execute(
                select(month, func.count())
                .where(ShelfEntry.shelf == "read", ShelfEntry.finished_at.is_not(None))
                .group_by(month)
            ).all()
        )
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
        "by_month": fill_months(by_month, date.today()),
    }
