import logging
import re
import time
from datetime import datetime
from urllib.parse import urlparse

import httpx

from shelfmate.agent.schemas import PriceOffer

log = logging.getLogger(__name__)
SEARX = "http://localhost:8080/search"
PRICE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)")
# Snippets often show the list price or the discount before the selling price.
NOT_PRICE_BEFORE = re.compile(r"(m\.?r\.?p\.?|save)\W*$", re.IGNORECASE)
NOT_PRICE_AFTER = re.compile(r"^\W*off\b", re.IGNORECASE)

NEW_STORES = ["amazon.in", "flipkart.com", "bookswagon.com", "sapnaonline.com"]
USED_STORES = ["bookchor.com", "kitabay.com"]
AUDIO_STORES = ["audible.in", "play.google.com"]


def searx(query: str) -> list[dict]:
    start = time.perf_counter()
    try:
        r = httpx.get(SEARX, params={"q": query, "format": "json"}, timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as e:
        # 403 here usually means searxng/settings.yml does not allow the json format.
        log.warning("Search failed", extra={"query": query, "error": str(e)})
        return []
    results = r.json()["results"][:10]
    ms = round((time.perf_counter() - start) * 1000, 1)
    log.debug(
        "Search returned %d results in %.1f ms",
        len(results),
        ms,
        extra={"query": query, "results": len(results), "duration_ms": ms},
    )
    return results


def selling_price(text: str) -> str | None:
    """The first amount in the text that is not an MRP, a 'Save' or an 'off' amount."""
    for m in PRICE.finditer(text):
        before, after = text[max(0, m.start() - 12) : m.start()], text[m.end() :]
        if not NOT_PRICE_BEFORE.search(before) and not NOT_PRICE_AFTER.match(after):
            return m.group(1)
    return None


def on_store(url: str, store: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == store or host.endswith("." + store)


def find_offer(title, isbn13, fmt, store, condition) -> PriceOffer | None:
    # ISBN queries often find no priced result, so fall back to title and format.
    # The generator only runs the second search if the first gives no offer.
    queries = [f"{title} {fmt} site:{store}"]
    if isbn13:
        queries.insert(0, f"{title} {isbn13} {fmt} site:{store}")
    for res in (r for q in queries for r in searx(q)):
        if not on_store(res["url"], store):
            continue
        raw = selling_price(res.get("content", ""))
        if not raw:
            continue
        try:
            offer = PriceOffer(
                title=title,
                store=store,
                format=fmt,
                condition=condition,
                price_inr=float(raw.replace(",", "")),
                url=res["url"],
                checked_at=datetime.now(),
            )
        except ValueError as e:
            log.warning(
                "Rejected a price that failed validation",
                extra={
                    "store": store,
                    "url": res["url"],
                    "raw_price": raw,
                    "reason": str(e).splitlines()[0],
                },
            )
            continue
        log.info(
            "Price found: %s (%s) at %s for Rs %.0f",
            title,
            fmt,
            store,
            offer.price_inr,
            extra={
                "isbn13": isbn13,
                "store": store,
                "book_format": fmt,
                "price_inr": offer.price_inr,
            },
        )
        return offer
    log.info(
        "No price found for %s (%s) at %s",
        title,
        fmt,
        store,
        extra={"isbn13": isbn13, "store": store, "book_format": fmt},
    )
    return None


if __name__ == "__main__":
    print(find_offer("Golden Son", "9781444759044", "paperback", "amazon.in", "new"))
