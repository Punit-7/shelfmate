import logging
import time

import httpx

from shelfmate.logging_setup import new_run, setup_logging

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Shelfmate/0.1 (punit251299@gmail.com)"}
BASE = "https://openlibrary.org"
COVER = "https://covers.openlibrary.org/b/id/{id}-M.jpg"


def _get(path: str, params: dict) -> dict:
    start = time.perf_counter()
    r = httpx.get(f"{BASE}{path}", params=params, headers=HEADERS, timeout=10)
    ms = round((time.perf_counter() - start) * 1000, 1)
    log.debug(
        "GET %s -> %d in %.1f ms",
        path,
        r.status_code,
        ms,
        extra={"url_path": path, "status": r.status_code, "duration_ms": ms},
    )
    if r.status_code == 429:
        log.warning("Open Library rate limit hit, slow down", extra={"url_path": path})
    r.raise_for_status()
    return r.json()


def search_book(title: str, author: str) -> dict | None:
    # The dataset lists every contributor ("J.K. Rowling, Mary GrandPré"), and Open Library
    # finds nothing when an illustrator or translator is included, so use the first author.
    # Free-text `q` (not `title`) also matches US/UK title variants, such as Sorcerer's
    # and Philosopher's Stone, and ranks the work with the most editions first.
    params = {"q": title, "author": author.split(",")[0].strip(), "limit": 1}
    docs = _get("/search.json", params)["docs"]
    if not docs:
        log.warning(
            "Book not found on Open Library", extra={"title": title, "author": author}
        )
        return None
    return docs[0]


def search_books(query: str, limit: int = 10) -> list[dict]:
    """Free-text search for the website's "add a book" box."""
    params = {
        "q": query,
        "limit": limit,
        "fields": "key,title,author_name,first_publish_year",
    }
    return [
        {
            "ol_work_id": d["key"],
            "title": d["title"],
            "author": ", ".join(d.get("author_name", [])) or "Unknown",
            "year": d.get("first_publish_year"),
        }
        for d in _get("/search.json", params)["docs"]
    ]


def works_by_author(author: str, limit: int = 10) -> list[dict]:
    """An author's works from Open Library, most-edited first, for authors the catalogue lacks."""
    params = {
        "author": author,
        "sort": "editions",
        "limit": limit,
        "fields": "title,author_name,first_publish_year",
    }
    return [
        {
            "title": d["title"],
            "author": ", ".join(d.get("author_name", [])) or author,
            "year": d.get("first_publish_year"),
        }
        for d in _get("/search.json", params)["docs"]
    ]


def new_books_by(author: str, since_year: int) -> list[dict]:
    """Works by an author first published in or after since_year, newest first."""
    params = {
        "author": author.split(",")[0].strip(),
        "sort": "new",
        "limit": 5,
        "fields": "key,title,first_publish_year",
    }
    docs = _get("/search.json", params)["docs"]
    return [d for d in docs if (d.get("first_publish_year") or 0) >= since_year]


def cover_loads(url: str) -> bool:
    """True if the address gives a real picture. A missing cover gives an error or a tiny image.

    A network error is not caught: it says nothing about the cover, so the lookup is
    tried again later instead of saving "no cover".
    """
    r = httpx.get(url, headers=HEADERS, timeout=10, follow_redirects=True)
    return (
        r.status_code == 200
        and r.headers.get("content-type", "").startswith("image/")
        and len(r.content) > 2000
    )


def english_cover(work_key: str) -> str | None:
    """The cover of an English edition of the work, or None.

    The work's own cover (cover_i) can be a foreign edition, so covers are taken from
    English editions only. A book with no English cover shows none, not a foreign one.
    """
    entries = _get(f"{work_key}/editions.json", {"limit": 50})["entries"]
    for e in entries:
        if "/languages/eng" not in [lang["key"] for lang in e.get("languages", [])]:
            continue
        for cover_id in e.get("covers", []):
            # -1 means "no cover", and a listed number can point at a picture that is gone.
            url = COVER.format(id=cover_id)
            if cover_id > 0 and cover_loads(url):
                return url
    return None


def get_editions(work_key: str) -> list[dict]:
    entries = _get(f"{work_key}/editions.json", {"limit": 50})["entries"]
    editions = []
    for e in entries:
        fmt = (e.get("physical_format") or "").lower()
        # ponytail: editions with no language recorded are kept, as many English ones have none
        langs = [lang["key"] for lang in e.get("languages", [])]
        if langs and "/languages/eng" not in langs:
            continue
        for isbn in e.get("isbn_13", []):
            if fmt in ("hardcover", "paperback"):
                editions.append({"isbn13": isbn, "format": fmt})
    log.info(
        "Found %d hardcover or paperback ISBNs",
        len(editions),
        extra={
            "work_key": work_key,
            "editions_checked": len(entries),
            "isbns": len(editions),
        },
    )
    return editions


def get_description(work_key: str) -> str | None:
    """The work's description text, or None if Open Library has none."""
    desc = _get(f"{work_key}.json", {}).get("description")
    if isinstance(desc, dict):
        desc = desc.get("value")
    return desc or None


if __name__ == "__main__":
    setup_logging("loader")
    new_run("openlibrary")
    book = search_book("Red Rising", "Pierce Brown")
    print(book["key"], book["title"], book.get("first_publish_year"))
    print(get_editions(book["key"])[:3])
