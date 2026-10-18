import logging
import time

import httpx

from shelfmate.logging_setup import new_run, setup_logging

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Shelfmate/0.1 (punit251299@gmail.com)"}
BASE = "https://openlibrary.org"


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
    docs = _get("/search.json", {"title": title, "author": author, "limit": 1})["docs"]
    if not docs:
        log.warning(
            "Book not found on Open Library", extra={"title": title, "author": author}
        )
        return None
    return docs[0]


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
