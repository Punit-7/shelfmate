import logging

from sqlalchemy import create_engine, text

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed
from shelfmate.recommender.lanes import parse_series

log = logging.getLogger("shelfmate.data.fill_series")


def fill_series() -> int:
    """Read the series name and number from each title, for books that have none yet.

    A title such as "Golden Son (Red Rising, #2)" gives "Red Rising" and 2.0.
    Returns how many books were updated. Safe to run again.
    """
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, title FROM books WHERE series_name IS NULL")
        ).all()

    updates = []
    for book_id, title in rows:
        name, pos = parse_series(title)
        if name:
            updates.append({"id": book_id, "name": name, "pos": pos})
    log.info(
        "Series found in titles",
        extra={"checked": len(rows), "in_series": len(updates)},
    )

    if updates:
        with timed(log, "fill series", rows=len(updates)), engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE books SET series_name = :name, series_pos = :pos WHERE id = :id"
                ),
                updates,
            )
    return len(updates)


if __name__ == "__main__":
    setup_logging("loader")
    new_run("fill-series")
    fill_series()
