import logging

log = logging.getLogger(__name__)


def minmax(scores: dict[int, float]) -> dict[int, float]:
    lo, hi = min(scores.values()), max(scores.values())
    return {k: (v - lo) / (hi - lo) if hi > lo else 0.0 for k, v in scores.items()}


def hybrid(cf: dict[int, float], content: dict[int, float], n_rated: int, n: int = 5):
    alpha = 0.3 if n_rated < 5 else 0.7
    if not cf and not content:
        log.warning("Both models returned nothing", extra={"n_rated": n_rated})
        return []
    cf = minmax(cf) if cf else {}
    content = minmax(content) if content else {}
    books = set(cf) | set(content)
    combined = {
        b: alpha * cf.get(b, 0) + (1 - alpha) * content.get(b, 0) for b in books
    }
    top = sorted(combined.items(), key=lambda x: x[1], reverse=True)[:n]
    log.info(
        "Hybrid ranked %d candidates",
        len(books),
        extra={
            "alpha": alpha,
            "n_rated": n_rated,
            "cf_candidates": len(cf),
            "content_candidates": len(content),
            "returned": len(top),
        },
    )
    log.debug(
        "Hybrid top scores", extra={"top": [(int(b), round(s, 3)) for b, s in top]}
    )
    return top
