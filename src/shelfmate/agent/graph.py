import logging

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from shelfmate.agent.tools import (
    find_audiobook,
    find_cheapest_prices,
    log_finished_book,
    recommend_books,
)
from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger(__name__)

SYSTEM = """You are Shelfmate, a book assistant for a reader in India.
Pass book titles to the tools exactly as the reader wrote them.
- The reader says they finished or read a book: call log_finished_book with its rating.
- The reader asks what to read next or wants suggestions: call recommend_books.
- The reader asks about prices, deals or where to buy: call find_cheapest_prices.
- The reader asks about audiobooks or listening: call find_audiobook.
A message can need more than one tool; call every tool it needs.
Only mention books, prices and links that a tool returned. If a tool returns
nothing, say so. Never invent titles or prices.
Show prices in rupees with the store name and link."""

# A stalled Ollama server would otherwise block a chat turn forever.
llm = ChatOllama(
    model=settings.llm_model,
    base_url=settings.ollama_url,
    temperature=0,
    client_kwargs={"timeout": 120},
)
agent = create_react_agent(
    llm,
    tools=[recommend_books, find_cheapest_prices, find_audiobook, log_finished_book],
    prompt=SYSTEM,
)


# Each tool round trip is two steps, so 10 allows about four tool calls per question.
LIMITS = {"recursion_limit": 10}


def tools_called(result: dict) -> list[str]:
    return [
        c["name"]
        for m in result["messages"]
        for c in getattr(m, "tool_calls", None) or []
    ]


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
