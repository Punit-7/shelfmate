import html
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from prefect import flow, task
from sqlalchemy import select
from sqlalchemy.orm import Session

from shelfmate.agent.tools import engine
from shelfmate.data.openlibrary import new_books_by
from shelfmate.db.models import Book, ShelfEntry
from shelfmate.logging_setup import new_run, setup_logging
from shelfmate.notify import email_ready, send_email

log = logging.getLogger("shelfmate.flows.weekly")


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


def email_html(releases: list[dict]) -> str:
    parts = ["<h2>New books by authors you like</h2>"]
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
    releases = find_new_releases()
    if not releases:
        log.info("No new releases this week, no email")
    elif not email_ready():
        log.warning("Email is not set up in .env, skipping the email")
    else:
        send_email("Shelfmate: new books by authors you like", email_html(releases))
    log.info("Weekly refresh finished")


WHEN = ZoneInfo(
    "Asia/Kolkata"
)  # the weekly run is at 9am in India, not in the container's UTC
SUNDAY = 6  # datetime.weekday(): Monday is 0


def next_sunday_nine(now: datetime) -> datetime:
    """The next Sunday at 9am after now. On a Sunday before 9am, that is today."""
    days = (SUNDAY - now.weekday()) % 7
    run = (now + timedelta(days=days)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    return run if run > now else run + timedelta(days=7)


def run_every_sunday() -> None:
    """Sleeps until the next Sunday at 9am, runs the refresh, and repeats. A failed run is logged and the loop goes on."""
    while True:
        run_at = next_sunday_nine(datetime.now(WHEN))
        log.info("Next weekly refresh", extra={"at": run_at.isoformat()})
        time.sleep((run_at - datetime.now(WHEN)).total_seconds())
        try:
            weekly_refresh()
        except Exception:
            log.exception("Weekly refresh failed, trying again next Sunday")


if __name__ == "__main__":
    setup_logging("worker")
    run_every_sunday()
