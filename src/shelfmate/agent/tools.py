import functools
import logging

from langchain_core.tools import tool

from shelfmate.logging_setup import timed

log = logging.getLogger(__name__)


def log_tool(fn):
    """Logs each tool call: its arguments, how long it took and what it returned."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        log.info(
            "Tool called: %s",
            fn.__name__,
            extra={"tool": fn.__name__, "tool_args": kwargs},
        )
        with timed(log, f"tool {fn.__name__}", tool=fn.__name__):
            result = fn(*args, **kwargs)
        count = len(result) if isinstance(result, list) else 1
        log.debug(
            "Tool returned %d result(s)",
            count,
            extra={"tool": fn.__name__, "result": result},
        )
        if count == 0:
            log.warning(
                "Tool %s returned nothing",
                fn.__name__,
                extra={"tool": fn.__name__, "tool_args": kwargs},
            )
        return result

    return wrapper


@tool
@log_tool
def recommend_books(n: int = 5) -> list[dict]:
    """Return the top n hybrid recommendations for the user, with book_id and title."""


@tool
@log_tool
def find_cheapest_prices(book_id: int) -> list[dict]:
    """Find the cheapest new and used hardcover and paperback prices in India for a book."""


@tool
@log_tool
def find_audiobook(book_id: int) -> list[dict]:
    """Find audiobook listings for a book on Audible India and Google Play Books."""


@tool
@log_tool
def log_finished_book(title: str, rating: int) -> str:
    """Mark a book as finished on the user's shelf with a rating from 1 to 5."""
