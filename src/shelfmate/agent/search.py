import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import unescape
from urllib.parse import quote_plus, unquote_plus, urlparse

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
    "audible.in": "https://www.audible.in/search?keywords={q}",
}
NEW_STORES = ["amazon.in", "flipkart.com", "bookswagon.com"]
AUDIO_STORES = ["audible.in"]

# Checking that a store shows the book before we link to it.
BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-IN,en;q=0.9",
}
STOCK_TTL = 24 * 3600  # a store's catalogue changes slowly
RETRY_AFTER = 15 * 60  # a store that blocked or failed us is asked again soon
MIN_PAGE = (
    20_000  # a blocked request gets a page of about 2 KB, a results page is far bigger
)
# ponytail: in memory, lost on restart. Keep it in a table if restarts make the first page slow.
_stock: dict[tuple[str, str, str], tuple[float, bool]] = {}


def store_links(title: str, author: str, stores: list[str]) -> list[dict]:
    """A search page on each store for this book. The store shows the current price."""
    # The series part and a second author make worse searches, so leave them out.
    q = quote_plus(f"{title.split(' (')[0]} {author.split(',')[0]}".strip())
    return [{"store": s, "url": SEARCH_PAGES[s].format(q=q)} for s in stores]


def shows_book(page: str, title: str, author: str) -> bool:
    """True if a store's search page lists this book: the title and the author close together.

    Every page repeats what we searched for, in its title and search box, so that text is
    removed first. Without that, a store with no match would still look like it has one.
    """
    short, first = title.split(" (")[0], author.split(",")[0].strip()
    text = words(unescape(re.sub(r"<[^>]+>", " ", unquote_plus(page))))
    text = text.replace(words(f"{short} {first}"), " ")
    t = re.escape(words(short))
    if not first:
        return re.search(rf"\b{t}\b", text) is not None
    a = re.escape(words(first).split()[-1])
    return (
        re.search(rf"\b{t}\b.{{0,300}}\b{a}\b|\b{a}\b.{{0,300}}\b{t}\b", text)
        is not None
    )


def in_stock(store: str, title: str, author: str) -> bool:
    """False only when the store's search page loaded and does not show this book.

    A page that fails, is blocked or is too small to be a results page means "we do not
    know", so the link stays. Hiding a store we could not check would be worse than showing
    a link to a page without the book.
    """
    key = (store, title, author)
    hit = _stock.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    url = store_links(title, author, [store])[0]["url"]
    try:
        r = httpx.get(url, headers=BROWSER, timeout=10, follow_redirects=True)
        r.raise_for_status()
        page = r.text
    except httpx.HTTPError as e:
        log.info("Store not checked", extra={"store": store, "error": str(e)})
        page = ""
    if len(page) < MIN_PAGE:
        ok, ttl = True, RETRY_AFTER
    else:
        ok, ttl = shows_book(page, title, author), STOCK_TTL
        if not ok:
            log.info("Not listed at %s: %s", store, title, extra={"store": store})
    _stock[key] = (time.time() + ttl, ok)
    return ok


def stocked_links(books: list[tuple[str, str]], stores: list[str]) -> list[list[dict]]:
    """store_links for each (title, author), keeping the stores that show the book.

    All the checks run together, so a list of books takes about as long as one page load.
    """
    pairs = [(s, t, a) for t, a in books for s in stores]
    with ThreadPoolExecutor(max_workers=12) as pool:
        stocked = iter(pool.map(lambda p: in_stock(*p), pairs))
    return [
        [link for link in store_links(t, a, stores) if next(stocked)] for t, a in books
    ]


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
