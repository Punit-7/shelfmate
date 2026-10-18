import logging
import re
import time
from datetime import datetime
from urllib.parse import quote_plus, urlparse

import httpx

from shelfmate.agent.schemas import PriceOffer
from shelfmate.config import settings

log = logging.getLogger(__name__)
SEARX = f"{settings.searxng_url}/search"
PRICE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)")
# Snippets often show the list price or the discount before the selling price.
NOT_PRICE_BEFORE = re.compile(r"(m\.?r\.?p\.?|save)\W*$", re.IGNORECASE)
NOT_PRICE_AFTER = re.compile(r"^\W*off\b", re.IGNORECASE)

# "5 books collection set" and similar are not the single book.
BUNDLE = re.compile(r"\b(\d+ books?|box set|boxset|combo|collection|bundle|set of)\b")

# Search pages on each store. We link to them instead of reading prices, so no store API is needed.
SEARCH_PAGES = {
    "amazon.in": "https://www.amazon.in/s?k={q}",
    "flipkart.com": "https://www.flipkart.com/search?q={q}",
    "bookswagon.com": "https://www.bookswagon.com/search-books/{q}",
    "sapnaonline.com": "https://www.sapnaonline.com/search?q={q}",
    "audible.in": "https://www.audible.in/search?keywords={q}",
}
NEW_STORES = ["amazon.in", "flipkart.com", "bookswagon.com", "sapnaonline.com"]
AUDIO_STORES = ["audible.in"]


def store_links(title: str, author: str, stores: list[str]) -> list[dict]:
    """A search page on each store for this book. The store shows the current price."""
    # The series part and a second author make worse searches, so leave them out.
    q = quote_plus(f"{title.split(' (')[0]} {author.split(',')[0]}".strip())
    return [{"store": s, "url": SEARCH_PAGES[s].format(q=q)} for s in stores]


def searx(query: str) -> list[dict]:
    start = time.perf_counter()
    try:
        r = httpx.get(SEARX, params={"q": query, "format": "json"}, timeout=15)
        r.raise_for_status()
        results = r.json()["results"][:10]
    except (httpx.HTTPError, ValueError, KeyError) as e:
        # 403 here usually means searxng/settings.yml does not allow the json format.
        log.warning("Search failed", extra={"query": query, "error": str(e)})
        return []
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


def words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def is_this_book(text: str, own: str, title: str, author: str) -> bool:
    """True if a result is about this book, not another book or a box set.

    text is everything the result says. own is its page title and address, which must
    name the book: a Golden Son page can mention Morning Star in its description.
    Without the author, "Hopeless" matches Elsie Silver's Hopeless as readily as Colleen Hoover's.
    """
    t = words(text)
    if words(title) not in words(own):
        return False
    if author and words(author).split()[-1] not in t:
        return False
    return not (BUNDLE.search(t) and not BUNDLE.search(words(title)))


def format_of(text: str, formats: tuple[str, ...]) -> str | None:
    """Which of the wanted formats the text is about. None if it names none or several."""
    if len(formats) == 1:
        return formats[0]
    t = words(text)
    found = [f for f in formats if f in t]
    return found[0] if len(found) == 1 else None


def find_offers(title, author, formats, store, condition) -> list[PriceOffer]:
    """The cheapest valid price per format for this book at this store.

    One search per store, not per format, because each search can trigger the
    upstream engines' rate limits. The author goes into the query and the relevance
    check, because a title alone matches other books.
    ponytail: snippets only; many store pages show no price in the snippet, so some
    books get no offer. Reading the page's own price would fix that.
    """
    first_author = author.split(",")[0].strip()
    audio = formats == ("audiobook",)
    query = f"{title} {first_author} {'audiobook' if audio else ''} site:{store}"
    best: dict[str, PriceOffer] = {}
    for res in searx(" ".join(query.split())):
        text = f"{res.get('title', '')} {res.get('content', '')}"
        own = f"{res.get('title', '')} {res['url']}"
        if not on_store(res["url"], store) or not is_this_book(
            f"{text} {res['url']}", own, title, first_author
        ):
            continue
        fmt, raw = format_of(f"{text} {res['url']}", formats), selling_price(text)
        if not (fmt and raw):
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
        if fmt not in best or offer.price_inr < best[fmt].price_inr:
            best[fmt] = offer
    for fmt, offer in best.items():
        log.info(
            "Price found: %s (%s) at %s for Rs %.0f",
            title,
            fmt,
            store,
            offer.price_inr,
            extra={"store": store, "book_format": fmt, "price_inr": offer.price_inr},
        )
    if not best:
        log.info("No price found for %s at %s", title, store, extra={"store": store})
    return list(best.values())


if __name__ == "__main__":
    print(
        find_offers(
            "Golden Son", "Pierce Brown", ("paperback", "hardcover"), "amazon.in", "new"
        )
    )
