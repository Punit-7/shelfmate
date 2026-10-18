import html
import logging
from datetime import date

import httpx
from prefect import flow, task
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shelfmate.agent.tools import engine
from shelfmate.data.openlibrary import new_books_by
from shelfmate.db.models import Book, Price, ShelfEntry
from shelfmate.flows.pipeline import get_prices, offer_line, save_prices
from shelfmate.logging_setup import new_run, setup_logging
from shelfmate.notify import email_ready, send_email

log = logging.getLogger("shelfmate.flows.weekly")


@task
def refresh_want_to_read() -> list[dict]:
    """Searches prices again for every Want to Read book. Returns the ones that got cheaper."""
    with Session(engine) as session:
        books = session.execute(
            select(Book.id, Book.title)
            .join(ShelfEntry, ShelfEntry.book_id == Book.id)
            .where(ShelfEntry.shelf == "to-read")
        ).all()
    drops = []
    for book_id, title in books:
        with Session(engine) as session:
            old = session.scalar(
                select(func.min(Price.price_inr)).where(Price.book_id == book_id)
            )
        offers = get_prices({"book_id": book_id, "title": title}, reuse_hours=0)
        with Session(engine) as session, session.begin():
            save_prices(session, book_id, offers)
        cheapest = min(offers, key=lambda o: o["price_inr"], default=None)
        if old and cheapest and cheapest["price_inr"] < old:
            drops.append({"title": title, "was": old, "offer": cheapest})
    log.info("Prices refreshed", extra={"books": len(books), "drops": len(drops)})
    return drops


@task
def find_new_releases() -> list[dict]:
    """Books from this year or last by authors you rated 4 or more, not yet in the catalogue."""
    with Session(engine) as session:
        authors = session.scalars(
            select(Book.author)
            .join(ShelfEntry, ShelfEntry.book_id == Book.id)
            .where(ShelfEntry.rating >= 4)
            .distinct()
        ).all()
        known = {t.lower() for t in session.scalars(select(Book.title))}
    since = date.today().year - 1
    found = []
    for author in authors:
        try:
            works = new_books_by(author, since)
        except httpx.HTTPError:
            log.warning("Open Library failed for one author", exc_info=True)
            continue
        found += [
            {"title": w["title"], "author": author, "year": w["first_publish_year"]}
            for w in works
            if w["title"].lower() not in known
        ]
    log.info("New releases found", extra={"authors": len(authors), "new": len(found)})
    return found


def email_html(drops: list[dict], releases: list[dict]) -> str:
    parts = ["<h2>Price drops on your Want to Read shelf</h2>"]
    parts += [
        f"<p><b>{html.escape(d['title'])}</b>: was Rs {d['was']:,.0f}, now "
        f"{offer_line(d['offer'])}</p>"
        for d in drops
    ] or ["<p>No price drops this week.</p>"]
    parts.append("<h2>New books by authors you like</h2>")
    parts += [
        f"<p><b>{html.escape(r['title'])}</b> by {html.escape(r['author'])} "
        f"({r['year']})</p>"
        for r in releases
    ] or ["<p>No new releases this week.</p>"]
    return "\n".join(parts)


@flow(name="weekly-refresh")
def weekly_refresh():
    new_run("weekly")
    log.info("Weekly refresh started")
    drops = refresh_want_to_read()
    releases = find_new_releases()
    if not (drops or releases):
        log.info("Nothing new this week, no email")
    elif not email_ready():
        log.warning("Email is not set up in .env, skipping the email")
    else:
        send_email("Shelfmate: your weekly update", email_html(drops, releases))
    log.info("Weekly refresh finished")


if __name__ == "__main__":
    setup_logging("worker")
    weekly_refresh.serve(name="sunday-9am", cron="0 9 * * 0")
