import logging
import re

import httpx
from langchain_ollama import ChatOllama

from shelfmate.config import settings
from shelfmate.data.openlibrary import get_description, search_book
from shelfmate.logging_setup import timed

log = logging.getLogger(__name__)
MODEL = settings.llm_model
# A stalled Ollama server would otherwise block the pipeline forever.
llm = ChatOllama(
    model=MODEL,
    base_url=settings.ollama_url,
    temperature=0,
    client_kwargs={"timeout": 120},
)

PROMPT = """You write short book summaries for a reading app.
Use ONLY the description between the tags. Do not add names, places or events that are not in it.
Write at most 2 sentences and at most 45 words. Do not reveal the ending.
If the description is too short to summarise, reply with exactly: INSUFFICIENT

<description>
{description}
</description>"""

STOP = {
    "A",
    "An",
    "The",
    "He",
    "She",
    "It",
    "They",
    "His",
    "Her",
    "Their",
    "When",
    "In",
    "On",
    "At",
    "After",
    "Before",
    "This",
    "As",
    "But",
    "And",
    "With",
    "To",
    "For",
}


def unsupported_words(summary: str, description: str) -> list[str]:
    """Capitalised words and numbers in the summary that never appear in the description."""
    source = description.lower()
    words = re.findall(r"\b[A-Z][a-zA-Z'-]+\b|\b\d[\d,.]*\b", summary)
    return [w for w in words if w not in STOP and w.lower() not in source]


def trim(description: str, sentences: int = 2, max_chars: int = 300) -> str:
    """The first sentences of the description, cut at a word boundary."""
    parts = re.split(r"(?<=[.!?])\s+", description.strip())
    text = " ".join(parts[:sentences])
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] + "…"
    return text


def summarise(book_id: int, description: str | None) -> tuple[str, str]:
    """Returns (summary, source). Source is 'llm', 'description' or 'none'."""
    if not description:
        log.warning("No description, no summary", extra={"book_id": book_id})
        return "No summary available yet.", "none"
    if len(description.split()) < 25:
        log.info(
            "Description is short, showing it as it is", extra={"book_id": book_id}
        )
        return trim(description), "description"
    with timed(log, "summary", book_id=book_id, model=MODEL):
        text = llm.invoke(PROMPT.format(description=description)).content.strip()
    bad = unsupported_words(text, description)
    words = len(text.split())
    if text == "INSUFFICIENT" or bad or words > 45:
        log.warning(
            "LLM summary rejected, using description",
            extra={
                "book_id": book_id,
                "unsupported": bad,
                "words": words,
                "llm_text": text,
            },
        )
        return trim(description), "description"
    log.info("LLM summary accepted", extra={"book_id": book_id, "words": words})
    return text, "llm"


def fetch_description(book) -> None:
    """Finds the book on Open Library if needed, and keeps its work ID and description."""
    if book.description:
        return
    try:
        if book.ol_work_id is None:
            hit = search_book(book.title.split(" (")[0], book.author)
            book.ol_work_id = hit["key"] if hit else None
        if book.ol_work_id:
            book.description = get_description(book.ol_work_id)
    except httpx.HTTPError:
        log.exception("Open Library lookup failed", extra={"book_id": book.id})


def get_summary(session, book) -> tuple[str, str]:
    """Uses the saved summary if there is one. Otherwise creates it once and saves it."""
    if book.summary and book.summary_source != "none":
        return book.summary, book.summary_source
    fetch_description(book)
    book.summary, book.summary_source = summarise(book.id, book.description)
    book.summary_model = MODEL
    session.commit()
    return book.summary, book.summary_source
