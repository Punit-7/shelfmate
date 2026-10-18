import html
import logging
from datetime import datetime, timedelta

import httpx
from prefect import flow, task
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from shelfmate.agent.tools import (
    AUDIO_JOBS,
    PRINT_JOBS,
    engine,
    recommend,
    search_offers,
)
from shelfmate.data.openlibrary import english_cover, search_book
from shelfmate.db.models import Book, Price, Recommendation
from shelfmate.logging_setup import new_run, timed
from shelfmate.notify import email_ready, send_email
from shelfmate.recommender.summaries import get_summary

log = logging.getLogger(__name__)


@task(retries=3, retry_delay_seconds=[10, 20, 40])
def get_recommendations(n: int = 5) -> list[dict]:
    return recommend(n)


@task(retries=3, retry_delay_seconds=[10, 20, 40])
def get_prices(book: dict, reuse_hours: int = 24) -> list[dict]:
    """Offers for a book. Prices saved in the last reuse_hours are used instead of searching."""
    since = datetime.now() - timedelta(hours=reuse_hours)
    with Session(engine) as session:
        saved = session.scalars(
            select(Price).where(
                Price.book_id == book["book_id"], Price.checked_at > since
            )
        ).all()
    if saved:
        log.info("Using saved prices", extra={"book_id": book["book_id"]})
        return [
            {
                "store": p.store,
                "format": p.format,
                "condition": p.condition,
                "price_inr": p.price_inr,
                "url": p.url,
                "checked_at": p.checked_at.isoformat(),
            }
            for p in saved
        ]
    offers = search_offers(book["title"], PRINT_JOBS + AUDIO_JOBS)
    log.info(
        "Found %d offers for %s",
        len(offers),
        book["title"],
        extra={"book_id": book["book_id"], "offers": len(offers)},
    )
    if not offers:
        log.warning("No prices found", extra={"book_id": book["book_id"]})
    return offers


def ensure_cover(book_id: int) -> None:
    """Looks the book up on Open Library once, and saves its work ID and cover address."""
    with Session(engine) as session:
        book = session.get(Book, book_id)
        if book is None or book.cover_url is not None:
            return
        try:
            hit = search_book(book.title.split(" (")[0], book.author)
        except httpx.HTTPError:
            log.warning(
                "Open Library lookup failed", extra={"book_id": book_id}, exc_info=True
            )
            return
        book.ol_work_id = book.ol_work_id or (hit["key"] if hit else None)
        # "" means looked up, no English cover. None means not looked up yet.
        book.cover_url = (
            english_cover(book.ol_work_id) if book.ol_work_id else None
        ) or ""
        session.commit()


@task
def fill_details(book_id: int) -> None:
    """The cover, then a summary. A failure only costs these, not the run."""
    ensure_cover(book_id)
    try:
        with Session(engine) as session:
            get_summary(session, session.get(Book, book_id))
    except Exception:
        log.warning("No summary this run", extra={"book_id": book_id}, exc_info=True)


def save_prices(session: Session, book_id: int, offers: list[dict]) -> None:
    """Replaces the book's saved prices. Keeps the old ones if the search found nothing."""
    if not offers:
        return
    session.execute(delete(Price).where(Price.book_id == book_id))
    session.execute(
        insert(Price),
        [
            {
                "book_id": book_id,
                "store": o["store"],
                "format": o["format"],
                "condition": o["condition"],
                "price_inr": o["price_inr"],
                "url": o["url"],
                "checked_at": datetime.fromisoformat(o["checked_at"]),
            }
            for o in offers
        ],
    )


def offer_line(offer: dict) -> str:
    return (
        f'Rs {offer["price_inr"]:,.0f} at <a href="{html.escape(offer["url"])}">'
        f"{html.escape(offer['store'])}</a> ({offer['condition']} {offer['format']})"
    )


def email_html(results: list[dict]) -> str:
    parts = ["<h2>Your next books</h2>"]
    for r in results:
        cheapest = min(r["offers"], key=lambda o: o["price_inr"], default=None)
        parts.append(
            f"<h3>{html.escape(r['title'])}</h3>"
            f"<p>{html.escape(r['author'])}<br><i>{html.escape(r['because'])}</i></p>"
            f"<p>{offer_line(cheapest) if cheapest else 'No price found yet.'}</p>"
        )
    return "\n".join(parts)


@task
def save_and_email(results: list[dict]) -> None:
    """Replaces the Recommendations shelf and the prices, then emails the list."""
    with Session(engine) as session, session.begin():
        session.execute(delete(Recommendation))
        for rank, r in enumerate(results):
            session.add(
                Recommendation(
                    book_id=r["book_id"],
                    lane=r["lane"],
                    rank=rank,
                    because=r["because"],
                )
            )
            save_prices(session, r["book_id"], r["offers"])
            r["author"] = session.get(Book, r["book_id"]).author
    if not email_ready():
        log.warning("Email is not set up in .env, skipping the email")
        return
    send_email(f"Shelfmate: {len(results)} books to read next", email_html(results))


@flow(name="after-finished-book")
def after_finished_book():
    new_run("flow")
    log.info("Pipeline started")
    with timed(log, "after-finished-book flow"):
        books = get_recommendations()
        if not books:
            log.warning("No recommendations, nothing to price or email")
            return
        for b in books:
            fill_details(b["book_id"])
        results = [{**b, "offers": get_prices(b)} for b in books]
        save_and_email(results)
    log.info("Sent %d recommendations", len(results), extra={"books": len(results)})
