import logging
import re
from collections import Counter

log = logging.getLogger(__name__)

# "(Red Rising, #2)". A book in two series, "(Discworld, #16; Death, #3)", keeps the first.
SERIES = re.compile(r"\((?P<name>[^()#]+?),\s*#(?P<pos>[\d.]+)(?:[;,][^)]*)?\)\s*$")


def parse_series(title: str):
    m = SERIES.search(title)
    if not m:
        return None, None
    return m["name"].strip(), float(m["pos"])


def next_in_series(read, books):
    """read: your Read shelf with series_name, series_pos and rating.

    Returns the book id of the next numbered book in each series you rated 3 or more.
    """
    in_series = read.dropna(subset=["series_name"]).sort_values("series_pos")
    latest = in_series.groupby("series_name").last()
    picks = []
    for name, row in latest.iterrows():
        if row["rating"] < 3:
            log.debug(
                "Not continuing %s, last rating was %s",
                name,
                row["rating"],
                extra={"series": name},
            )
            continue
        later = books[
            (books.series_name == name)
            & (books.series_pos > row["series_pos"])
            & (books.series_pos % 1 == 0)
        ]
        if later.empty:
            log.info(
                "No next book for %s in the dataset, check Open Library",
                name,
                extra={"series": name, "last_pos": float(row["series_pos"])},
            )
            continue
        picks.append(int(later.nsmallest(1, "series_pos").index[0]))
    log.info(
        "Continue lane has %d book(s)",
        len(picks),
        extra={"series_started": len(latest), "picks": picks},
    )
    return picks


def something_new(ranked, books, started, first_book, n=5, per_author=2):
    """ranked: hybrid results, best first. started: every series you have read from."""
    used, authors, out = set(started), Counter(), []
    skipped = Counter()
    for book_id, score in ranked:
        name = books.loc[book_id, "series_name"]
        has_series = isinstance(name, str)
        if has_series and name in used:
            skipped["series already used"] += 1
            continue
        if has_series:
            book_id = first_book[name]
            used.add(name)
        author = books.loc[book_id, "author"]
        if authors[author] == per_author:
            skipped["author limit"] += 1
            continue
        authors[author] += 1
        out.append((book_id, score))
        if len(out) == n:
            break
    log.info(
        "New lane has %d book(s) from %d candidates",
        len(out),
        len(ranked),
        extra={"skipped": dict(skipped)},
    )
    if len(out) < n:
        log.warning(
            "New lane is short, ask the hybrid model for more candidates",
            extra={"wanted": n, "got": len(out)},
        )
    return out
