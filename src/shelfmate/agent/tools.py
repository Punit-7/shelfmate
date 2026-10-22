import functools
import logging
import re
from datetime import datetime

import httpx
import numpy as np
import pandas as pd
from langchain_core.tools import tool
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql import insert

from shelfmate.agent.search import AUDIO_STORES, NEW_STORES, stocked_links
from shelfmate.config import settings
from shelfmate.data.openlibrary import works_by_author
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
    # Books marked "not interested" are left out too, the same way.
    on_shelf |= set(
        pd.read_sql("SELECT book_id FROM dismissed_books", engine)["book_id"]
    )
    read = shelf[shelf["shelf"] == "read"]
    reading = shelf[shelf["shelf"] == "currently-reading"]
    liked = read.loc[read["rating"] >= 4, "book_id"].tolist()
    # A book you are reading shows what you like right now, so it counts as liked until you rate it.
    liked += [b for b in reading["book_id"] if b not in liked]
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

    # Series you are reading count as started too, so their next book is offered. Rating 3 is
    # the bar next_in_series uses, so an unrated book in progress passes it.
    read = pd.concat([read, reading.assign(rating=3)]).join(books, on="book_id")
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


def with_details(picks: list[dict]) -> list[dict]:
    """Adds each book's real author and summary, so the model has nothing to invent."""
    ids = [p["book_id"] for p in picks]
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, author, summary FROM books WHERE id = ANY(:ids)"),
            {"ids": ids},
        ).all()
    info = {r.id: (r.author, r.summary) for r in rows}
    return [
        {**p, "author": info[p["book_id"]][0], "summary": info[p["book_id"]][1]}
        for p in picks
    ]


@tool
@log_tool
def recommend_books(n: int = 5) -> list[dict]:
    """The reader's own recommendations, built from the books on their shelves. Use this when
    they ask what to read next without naming a book, series, author or kind of story."""
    return with_details(recommend(n))


def hidden_ids() -> list[int]:
    """Books on any shelf or marked not interested. They are never recommended."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT book_id FROM my_shelf UNION SELECT book_id FROM dismissed_books"
            )
        ).all()
    return [r[0] for r in rows] or [0]  # ANY(empty list) would match nothing useful


def find_seed(about: str):
    """The catalogue book the reader means: the exact title, or a title that starts with
    their words ("Ender" finds "Ender's Game"). A word inside a title does not count."""
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, title, author FROM books "
                "WHERE lower(split_part(title, ' (', 1)) = lower(:t) "
                r"OR title ~* ('^' || :pattern || '(\W|$)') "
                "ORDER BY lower(split_part(title, ' (', 1)) = lower(:t) DESC, length(title) "
                "LIMIT 1"
            ),
            {"t": about.strip(), "pattern": re.escape(about.strip())},
        ).first()


def readers_also_liked(
    seed_id: int, short: str, hidden: list[int], n: int
) -> list[int]:
    """Book ids that readers of the seed also liked, from the collaborative model.

    The seed itself, its own series, and anything on your shelves are left out, because the
    reader asked for something new like it.
    """
    model, n_books = als_model()
    if (
        seed_id >= n_books
    ):  # added after the ratings were collected, so ALS has never seen it
        return []
    ids, _ = model.similar_items(seed_id, N=80)
    books = catalogue()
    out = []
    for i in (int(x) for x in ids):
        if i == seed_id or i in hidden or i not in books.index:
            continue
        if short.lower() in books.loc[i, "title"].lower():
            continue  # a title that contains the seed's is the same series
        out.append(i)
        if len(out) == n:
            break
    return out


@tool
@log_tool
def recommend_like(about: str, n: int = 5) -> list[dict]:
    """Books like something the reader named: a book, a series, an author or a kind of story
    ("dark fantasy with vampires"). Pass their words as `about`. Use this whenever the reader
    names something to be similar to."""
    n = max(1, min(n, 10))
    hidden = hidden_ids()
    seed = find_seed(about)
    ids: list[int] = []
    if seed is not None:
        ids = readers_also_liked(seed.id, short_title(seed.title), hidden, n)
        because = f"Readers who liked {short_title(seed.title)} also liked these"
        note = None
    if not ids:
        # Not a book we have ratings for, so match the reader's own words by genre and title.
        from shelfmate.recommender.content import embed

        vector = embed([about])[0].tolist()
        with engine.connect() as conn:
            ids = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT id FROM books WHERE embedding IS NOT NULL AND id <> ALL(:hidden) "
                        "ORDER BY embedding <=> CAST(:v AS vector) LIMIT :n"
                    ),
                    {"v": str(vector), "hidden": hidden, "n": n},
                )
            ]
        because = f"Matches your words “{about}” by genre and title"
        note = (
            f"“{about}” is not a book the catalogue has ratings for, so these are matched "
            "only by genre and title words. Say so, and do not claim they are similar in story."
        )
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, title, author, summary FROM books WHERE id = ANY(:ids)"),
            {"ids": ids or [0]},
        ).all()
    info = {r.id: r for r in rows}
    picks = [
        {
            "book_id": i,
            "title": info[i].title,
            "author": info[i].author,
            "summary": info[i].summary,
            "because": because,
        }
        for i in ids
        if i in info
    ]
    if note:
        for p in picks:
            p["note"] = note
    return picks


@tool
@log_tool
def books_by_author(author: str) -> list[dict]:
    """Every catalogue book by an author, in series order. Pass only the author's name, such as
    "R.F. Kuang", without words like "books" or "'s"."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, title, author, summary FROM books WHERE author ILIKE '%' || :a || '%' "
                "ORDER BY series_name NULLS LAST, series_pos NULLS LAST, title LIMIT 20"
            ),
            {"a": author.strip()},
        ).all()
    if rows:
        return [
            {
                "book_id": r.id,
                "title": r.title,
                "author": r.author,
                "summary": r.summary,
                "because": f"By {r.author}",
            }
            for r in rows
        ]
    # Not in the catalogue: list them from Open Library, the same source as the Add page.
    try:
        found = works_by_author(author.strip())
    except httpx.HTTPError:
        return []
    return [
        {
            "title": w["title"],
            "author": w["author"],
            "year": w["year"],
            "because": f"By {w['author']}",
            "note": "From Open Library, not in the reader's catalogue yet. They can add it on the Add a book page.",
        }
        for w in found
    ]


def shop_links(title: str, stores: list[str]) -> list[dict]:
    """Search links for a book on the stores that show it, using the catalogue's title and author."""
    found = find_book(title)
    book = (found.title, found.author) if found else (title, "")
    return stocked_links([book], stores)[0]


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
