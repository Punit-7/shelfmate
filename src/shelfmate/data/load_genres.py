"""Adds each book's genres from the goodbooks tag files. Run: uv run python -m shelfmate.data.load_genres"""

import logging

import pandas as pd
from sqlalchemy import create_engine, text

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger("shelfmate.data.load_genres")
RAW = "data/raw"
PER_BOOK = 4

# Readers' shelf labels ("to-read", "favorites", "owned") are not genres. Only these are kept.
GENRES = {
    "fantasy",
    "epic-fantasy",
    "high-fantasy",
    "urban-fantasy",
    "science-fiction",
    "dystopian",
    "post-apocalyptic",
    "cyberpunk",
    "space-opera",
    "paranormal",
    "supernatural",
    "vampires",
    "mythology",
    "horror",
    "mystery",
    "thriller",
    "crime",
    "suspense",
    "romance",
    "historical-fiction",
    "young-adult",
    "children",
    "classics",
    "humor",
    "adventure",
    "action",
    "war",
    "biography",
    "memoir",
    "history",
    "philosophy",
    "poetry",
    "graphic-novels",
    "comics",
    "manga",
    "contemporary",
    "literature",
    "science",
    "religion",
    "psychology",
    "business",
}
# Other names for the same genre, so the book's top tags are not counted twice.
ALIASES = {
    "sci-fi": "science-fiction",
    "scifi": "science-fiction",
    "ya": "young-adult",
    "childrens": "children",
    "classic": "classics",
    "dystopia": "dystopian",
    "historical": "historical-fiction",
    "graphic-novel": "graphic-novels",
    "comic": "comics",
    "humour": "humor",
}


def genres_by_book(
    tags: pd.DataFrame, book_tags: pd.DataFrame, books: pd.DataFrame
) -> dict[int, str]:
    """Maps each book id to its most-used genres, e.g. {858: "science-fiction, dystopian"}.

    tags: tag_id, tag_name. book_tags: goodreads_book_id, tag_id, count.
    books: book_id, goodreads_book_id (the ids the database uses).
    """
    tagged = book_tags.merge(tags, on="tag_id")
    tagged["genre"] = tagged["tag_name"].str.lower().map(lambda t: ALIASES.get(t, t))
    tagged = tagged[tagged["genre"].isin(GENRES)]
    # A book's tags can repeat a genre under two names, so count each genre once.
    per_genre = (
        tagged.groupby(["goodreads_book_id", "genre"])["count"].sum().reset_index()
    )
    per_genre = per_genre.sort_values(
        ["goodreads_book_id", "count"], ascending=[True, False]
    )
    top = per_genre.groupby("goodreads_book_id").head(PER_BOOK)
    names = top.groupby("goodreads_book_id")["genre"].agg(", ".join)
    ids = books.set_index("goodreads_book_id")["book_id"]
    return {int(ids[g]): text_ for g, text_ in names.items() if g in ids.index}


def load_genres(raw: str = RAW) -> int:
    """Writes the genres column for every book that has genre tags. Returns how many books got some."""
    tags = pd.read_csv(f"{raw}/tags.csv")
    book_tags = pd.read_csv(f"{raw}/book_tags.csv")
    books = pd.read_csv(f"{raw}/books.csv", usecols=["book_id", "goodreads_book_id"])
    with timed(log, "genres by book"):
        found = genres_by_book(tags, book_tags, books)
    rows = [{"id": book_id, "genres": genres} for book_id, genres in found.items()]
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("UPDATE books SET genres = :genres WHERE id = :id"), rows)
    log.info("Genres saved", extra={"books": len(rows)})
    return len(rows)


if __name__ == "__main__":
    setup_logging("loader")
    new_run("load-genres")
    load_genres()
