import logging
import re

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from shelfmate.agent.tools import (
    books_by_author,
    find_audiobook,
    find_cheapest_prices,
    log_finished_book,
    recommend_books,
    recommend_like,
)
from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger(__name__)

SYSTEM = """You are Shelfmate, a book assistant for a reader in India.
Pass book titles to the tools exactly as the reader wrote them.
- The reader says they finished or read a book: call log_finished_book with its rating.
- The reader names an author and asks for their books ("X's books", "books by X"): call
  books_by_author with the author's name only.
- The reader names a book, series or kind of story and wants something similar: call
  recommend_like with their words. Do not use recommend_books for that.
- The reader asks what to read next without naming anything: call recommend_books.
- The reader asks about prices, deals or where to buy: call find_cheapest_prices.
- The reader asks about audiobooks or listening: call find_audiobook.
A message can need more than one tool; call every tool it needs.
When the reader finished a book, call log_finished_book before recommend_books.
Only mention books and links that a tool returned. Never invent titles or prices.
Give each book's author exactly as the tool returned it. Describe a book only with the summary
the tool returned. If it returned no summary, give just the title and author.
If the reader named something the tool did not find, say so plainly instead of guessing.
When a tool returns several books, name every one of them, one per line, with its author.
The tools return search links, not prices: tell the reader to open a store's
link to see its current price."""

# A stalled Ollama server would otherwise block a chat turn forever. On a CPU-only PC the first
# answer loads the model (several minutes) and then writes slowly, so the limit is 15 minutes.
# keep_alive keeps the model in memory between questions, so only the first one pays the load.
llm = ChatOllama(
    model=settings.llm_model,
    base_url=settings.ollama_url,
    temperature=0,
    client_kwargs={"timeout": 900},
    keep_alive="30m",
)
agent = create_react_agent(
    llm,
    tools=[
        recommend_books,
        recommend_like,
        books_by_author,
        find_cheapest_prices,
        find_audiobook,
        log_finished_book,
    ],
    prompt=SYSTEM,
)


# Each tool round trip is two steps, so 10 allows about four tool calls per question.
# The model asks for several tools in one step, and LangGraph runs them at the same time by
# default. One at a time, in order, so recommend_books sees the book log_finished_book saved.
LIMITS = {"recursion_limit": 10, "max_concurrency": 1}


def tools_called(result: dict) -> list[str]:
    return [
        c["name"]
        for m in result["messages"]
        for c in getattr(m, "tool_calls", None) or []
    ]


URL = re.compile(r"https?://[^\s<>\"')\]]+")


def strip_unlisted_links(answer: str, result: dict) -> str:
    """Keeps only the links a tool returned. The model sometimes writes its own store links."""
    returned = set()
    for m in result["messages"]:
        if getattr(m, "type", "") == "tool":
            returned.update(u.rstrip(".,;:!?") for u in URL.findall(str(m.content)))

    def check(match: re.Match) -> str:
        url = match.group(0)
        core = url.rstrip(".,;:!?")  # a full stop after a link is not part of it
        if core in returned:
            return url
        return "[link removed]" + url[len(core) :]

    return URL.sub(check, answer)


def ask(question: str) -> dict:
    new_run("chat")
    log.info("Question received", extra={"chars": len(question)})
    with timed(log, "agent answer"):
        result = agent.invoke({"messages": [("user", question)]}, LIMITS)
    tools = tools_called(result)
    log.info(
        "Answered using %d tool call(s)",
        len(tools),
        extra={"tools": tools, "steps": len(result["messages"])},
    )
    return result


if __name__ == "__main__":
    setup_logging("agent")
    for m in ask("I finished Golden Son, 5 stars. What next?")["messages"]:
        m.pretty_print()
