import logging

import pandas as pd
from sqlalchemy import create_engine

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger("shelfmate.data.load_ratings")


def load_ratings(path: str = "data/raw/ratings.csv") -> int:
    engine = create_engine(settings.database_url)
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
    with timed(log, "load ratings", rows=len(ratings)):
        ratings.to_sql(
            "ratings", engine, if_exists="append", index=False, chunksize=50_000
        )
    return len(ratings)


if __name__ == "__main__":
    setup_logging("loader")
    new_run("load")
    load_ratings()
