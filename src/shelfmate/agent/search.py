import logging
import re
import time
from datetime import datetime

import httpx

from shelfmate.agent.schemas import PriceOffer

log = logging.getLogger(__name__)
SEARX = "http://localhost:8080/search"
PRICE = re.compile(r"(?:₹|Rs\.?|INR)\s?([\d,]+(?:\.\d{1,2})?)")

NEW_STORES = ["amazon.in", "flipkart.com", "bookswagon.com", "sapnaonline.com"]
USED_STORES = ["bookchor.com", "kitabay.com"]
AUDIO_STORES = ["audible.in", "play.google.com"]


def searx(query: str) -> list[dict]:
    start = time.perf_counter()
    r = httpx.get(SEARX, params={"q": query, "format": "json"}, timeout=15)
    r.raise_for_status()
    results = r.json()["results"][:5]
    ms = round((time.perf_counter() - start) * 1000, 1)
    log.debug(
        "Search returned %d results in %.1f ms",
        len(results),
        ms,
        extra={"query": query, "results": len(results), "duration_ms": ms},
    )
    return results


def find_offer(title, isbn13, fmt, store, condition) -> PriceOffer | None:
    for res in searx(f"{title} {isbn13} {fmt} site:{store}"):
        match = PRICE.search(res.get("content", ""))
        if not match:
            continue
        try:
            offer = PriceOffer(
                title=title,
                store=store,
                format=fmt,
                condition=condition,
                price_inr=float(match.group(1).replace(",", "")),
                url=res["url"],
                checked_at=datetime.now(),
            )
        except ValueError as e:
            log.warning(
                "Rejected a price that failed validation",
                extra={
                    "store": store,
                    "url": res["url"],
                    "raw_price": match.group(1),
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
