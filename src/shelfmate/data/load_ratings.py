import logging

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger("shelfmate.data.load_ratings")


def load_ratings(path: str = "data/raw/ratings.csv") -> int:
    """Load the ratings once. Returns how many rows were added (0 if the table is already filled)."""
    engine = create_engine(settings.database_url)
    if not inspect(engine).has_table("ratings"):
        raise RuntimeError(
            "The ratings table does not exist. Run `uv run alembic upgrade head` first."
        )
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT COUNT(*) FROM ratings")).scalar_one()
    if existing:
        log.warning(
            "ratings already holds %s rows, skipping the load",
            f"{existing:,}",
            extra={"rows": existing},
        )
        return 0

    ratings = pd.read_csv(path)
    log.info(
        "Read %s ratings from %s",
        f"{len(ratings):,}",
        path,
        extra={
            "rows": len(ratings),
            "users": int(ratings["user_id"].nunique()),
            "books": int(ratings["book_id"].nunique()),
        },
    )
    bad = ratings[~ratings["rating"].between(1, 5)]
    if len(bad):
        log.warning(
            "Dropping %d ratings outside 1-5", len(bad), extra={"rows": len(bad)}
        )
        ratings = ratings.drop(bad.index)
    # One transaction: if the load fails halfway, nothing is kept and it can be run again.
    with timed(log, "load ratings", rows=len(ratings)), engine.begin() as conn:
        ratings.to_sql(
            "ratings", conn, if_exists="append", index=False, chunksize=50_000
        )
    return len(ratings)


if __name__ == "__main__":
    setup_logging("loader")
    new_run("load")
    load_ratings()
