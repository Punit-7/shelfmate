import functools
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from langchain_core.tools import tool
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert

from shelfmate.agent.search import AUDIO_STORES, NEW_STORES, store_links
from shelfmate.config import settings
from shelfmate.db.models import Book, ShelfEntry
from shelfmate.logging_setup import timed
from shelfmate.recommender.collaborative import build_matrix, recommend_for_me, train
from shelfmate.recommender.explain import because_you_liked
from shelfmate.recommender.hybrid import hybrid
from shelfmate.recommender.lanes import next_in_series, something_new

log = logging.getLogger(__name__)
engine = create_engine(settings.database_url)

CANDIDATES = 50  # the lane filters remove many books, so rank more than we show
POPULAR = "One of the most-liked books among all readers"


def log_tool(fn):
    """Logs each tool call: which arguments it got, how long it took and how many results.

    Argument values and results are not logged, because they hold the reader's own data.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        log.info(
            "Tool called: %s",
            fn.__name__,
            extra={"tool": fn.__name__, "arg_names": sorted(kwargs)},
        )
        with timed(log, f"tool {fn.__name__}", tool=fn.__name__):
            result = fn(*args, **kwargs)
        count = len(result) if isinstance(result, list) else 1
        log.debug(
            "Tool returned %d result(s)",
            count,
            extra={"tool": fn.__name__, "results": count},
        )
        if count == 0:
            log.warning(
                "Tool %s returned nothing", fn.__name__, extra={"tool": fn.__name__}
            )
        return result

    return wrapper


def find_book(title: str):
    """The catalogue book that best matches a title, as a row with id, title and author, or None."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, title, author FROM books WHERE title ILIKE '%' || :t || '%' "
                # An exact match on the title without its "(Series, #N)" part comes first.
                "ORDER BY lower(split_part(title, ' (', 1)) = lower(:t) DESC, length(title) "
                "LIMIT 1"
            ),
            {"t": title},
        ).first()


def short_title(title: str) -> str:
    """'Golden Son (Red Rising, #2)' -> 'Golden Son', which searches better."""
    return title.split(" (")[0]


@functools.cache
def als_model():
    """Train ALS on all ratings once per process. Takes about a minute."""
    # ponytail: retrained on every start; save the model with MLflow if startup time matters
    ratings = pd.read_sql("SELECT user_id, book_id, rating FROM ratings", engine)
    matrix = build_matrix(ratings)
    return train(matrix), matrix.shape[1]


@functools.cache
def catalogue() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT id, title, author, series_name, series_pos FROM books",
        engine,
        index_col="id",
    )


def content_scores(liked: list[int]) -> dict[int, float]:
    """Cosine similarity of the closest books to the average of your liked books."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "WITH me AS (SELECT AVG(embedding) AS v FROM books WHERE id = ANY(:liked)) "
                "SELECT b.id, 1 - (b.embedding <=> me.v) FROM books b, me "
                "WHERE b.id <> ALL(:liked) ORDER BY b.embedding <=> me.v LIMIT :k"
            ),
            {"liked": liked, "k": CANDIDATES},
        ).all()
    return {book_id: float(sim) for book_id, sim in rows}


def popular_books(exclude: set[int], n: int) -> list[dict]:
    """Most-liked books in the dataset, for a reader with no liked books yet."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT r.book_id, b.title FROM ratings r JOIN books b ON b.id = r.book_id "
                "WHERE r.rating >= 4 GROUP BY r.book_id, b.title "
                "ORDER BY COUNT(*) DESC LIMIT :k"
            ),
            {"k": n + len(exclude)},
        ).all()
    picks = [r for r in rows if r.book_id not in exclude][:n]
    return [
        {"book_id": r.book_id, "title": r.title, "lane": "new", "because": POPULAR}
        for r in picks
    ]


def embeddings(ids: list[int]) -> dict[int, np.ndarray]:
    with engine.connect() as conn:
        rows = conn.execute(
            select(Book.id, Book.embedding).where(
                Book.id.in_(ids), Book.embedding.is_not(None)
            )
        ).all()
    return {book_id: np.asarray(emb, dtype=np.float32) for book_id, emb in rows}


def recommend(n: int = 5) -> list[dict]:
    """Both lanes: the next book in each series you are reading, then n new books.

    Each pick has book_id, title, lane ("continue" or "new") and a "because" line.
    """
    shelf = pd.read_sql("SELECT book_id, shelf, rating FROM my_shelf", engine)
    on_shelf = set(shelf["book_id"])  # every shelf, so you never get a book you own
    read = shelf[shelf["shelf"] == "read"]
    liked = read.loc[read["rating"] >= 4, "book_id"].tolist()
    if not liked:
        return popular_books(on_shelf, n)

    books = catalogue()
    model, n_books = als_model()
    # Books added from Open Library are newer than the ratings, so ALS cannot score them.
    cf_liked = [b for b in liked if b < n_books]
    cf = {
        int(b): float(s)
        for b, s in recommend_for_me(model, cf_liked, n_books, CANDIDATES)
    }
    rated = int((read["rating"] > 0).sum())
    ranked = hybrid(cf, content_scores(liked), n_rated=rated, n=CANDIDATES)
    ranked = [(b, s) for b, s in ranked if b in books.index and b not in on_shelf]

    read = read.join(books, on="book_id")
    first_book = (
        books.dropna(subset=["series_name"])
        .sort_values("series_pos")
        .reset_index()
        .groupby("series_name")["id"]
        .first()
        .to_dict()
    )
    started = set(read["series_name"].dropna())

    picks = [
        {
            "book_id": book_id,
            "title": books.loc[book_id, "title"],
            "lane": "continue",
            "because": f"Next in {books.loc[book_id, 'series_name']}",
        }
        for book_id in next_in_series(read, books)
        if book_id not in on_shelf
    ]
    new = [int(b) for b, _ in something_new(ranked, books, started, first_book, n=n)]
    vectors = embeddings(new + liked)
    liked_vectors = {books.loc[b, "title"]: vectors[b] for b in liked if b in vectors}
    picks += [
        {
            "book_id": b,
            "title": books.loc[b, "title"],
            "lane": "new",
            "because": because_you_liked(vectors.get(b), liked_vectors),
        }
        for b in new
    ]
    return picks


@tool
@log_tool
def recommend_books(n: int = 5) -> list[dict]:
    """Return the top n hybrid recommendations for the user, with book_id and title."""
    return recommend(n)


def shop_links(title: str, stores: list[str]) -> list[dict]:
    """Search links for a book on these stores, using the catalogue's title and author."""
    found = find_book(title)
    if found:
        return store_links(found.title, found.author, stores)
    return store_links(title, "", stores)


@tool
@log_tool
def find_cheapest_prices(title: str) -> list[dict]:
    """Store links for a book's print edition. Open them to see the current price."""
    return shop_links(title, NEW_STORES)


@tool
@log_tool
def find_audiobook(title: str) -> list[dict]:
    """Store links for a book's audiobook on Audible India."""
    return shop_links(title, AUDIO_STORES)


@tool
@log_tool
def log_finished_book(title: str, rating: int) -> str:
    """Mark a book as finished on the user's shelf with a rating from 1 to 5."""
    if not 1 <= rating <= 5:
        return "The rating must be from 1 to 5. Nothing was saved."
    book = find_book(title)
    if not book:
        return f"'{title}' is not in the catalogue, so it was not saved."
    stmt = insert(ShelfEntry).values(
        book_id=book.id,
        shelf="read",
        rating=rating,
        source="agent",
        finished_at=datetime.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["book_id"],
        set_={c: stmt.excluded[c] for c in ("shelf", "rating", "finished_at")},
    )
    with engine.begin() as conn:
        conn.execute(stmt)
    return f"Saved {book.title} as read, rated {rating}/5."
