import contextvars
import functools
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pandas as pd
from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert

from shelfmate.agent.search import AUDIO_STORES, NEW_STORES, USED_STORES, find_offer
from shelfmate.config import settings
from shelfmate.db.models import ShelfEntry
from shelfmate.logging_setup import timed
from shelfmate.recommender.collaborative import build_matrix, recommend_for_me, train
from shelfmate.recommender.hybrid import hybrid
from shelfmate.recommender.lanes import next_in_series, something_new

log = logging.getLogger(__name__)
engine = create_engine(settings.database_url)

CANDIDATES = 50  # the lane filters remove many books, so rank more than we show
PRINT_FORMATS = ["paperback", "hardcover"]


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
    """The catalogue book that best matches a title, as a row with id and title, or None."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, title FROM books WHERE title ILIKE '%' || :t || '%' "
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
    return [{"book_id": r.book_id, "title": r.title, "lane": "popular"} for r in picks]


@tool
@log_tool
def recommend_books(n: int = 5) -> list[dict]:
    """Return the top n hybrid recommendations for the user, with book_id and title."""
    shelf = pd.read_sql(
        "SELECT book_id, rating FROM my_shelf WHERE shelf = 'read'", engine
    )
    on_shelf = set(shelf["book_id"])
    liked = shelf.loc[shelf["rating"] >= 4, "book_id"].tolist()
    if not liked:
        return popular_books(on_shelf, n)

    books = catalogue()
    model, n_books = als_model()
    cf = {
        int(b): float(s) for b, s in recommend_for_me(model, liked, n_books, CANDIDATES)
    }
    rated = int((shelf["rating"] > 0).sum())
    ranked = hybrid(cf, content_scores(liked), n_rated=rated, n=CANDIDATES)
    ranked = [(b, s) for b, s in ranked if b in books.index and b not in on_shelf]

    read = shelf.join(books, on="book_id")
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
            "book_id": int(books.index[books["title"] == t][0]),
            "title": t,
            "lane": "continue your series",
        }
        for t in next_in_series(read, books)
    ]
    picks += [
        {"book_id": int(b), "title": books.loc[b, "title"], "lane": "something new"}
        for b, _ in something_new(ranked, books, started, first_book, n=n)
    ]
    return picks


def search_offers(title: str, jobs: list[tuple[str, str, str]]) -> list[dict]:
    """Run find_offer for each (format, store, condition) in parallel, cheapest first."""
    found = find_book(title)
    name = short_title(found.title) if found else title
    # Each thread gets a copy of this context, so search logs keep the chat's run ID.
    contexts = [contextvars.copy_context() for _ in jobs]
    with ThreadPoolExecutor(max_workers=4) as pool:
        offers = pool.map(
            lambda ctx, job: ctx.run(find_offer, name, None, *job), contexts, jobs
        )
        offers = sorted((o for o in offers if o), key=lambda o: o.price_inr)
    return [o.model_dump(mode="json") for o in offers]


@tool
@log_tool
def find_cheapest_prices(title: str) -> list[dict]:
    """Find the cheapest new and used hardcover and paperback prices in India for a book."""
    jobs = [(f, s, "new") for s in NEW_STORES for f in PRINT_FORMATS]
    jobs += [(f, s, "used") for s in USED_STORES for f in PRINT_FORMATS]
    cheapest = {}
    for offer in search_offers(title, jobs):
        cheapest.setdefault((offer["format"], offer["condition"]), offer)
    return list(cheapest.values())


@tool
@log_tool
def find_audiobook(title: str) -> list[dict]:
    """Find audiobook listings for a book on Audible India and Google Play Books."""
    return search_offers(title, [("audiobook", s, "new") for s in AUDIO_STORES])


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
