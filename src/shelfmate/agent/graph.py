import logging

from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from shelfmate.agent.tools import (
    recommend_books,
    find_cheapest_prices,
    find_audiobook,
    log_finished_book,
)
from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger(__name__)

SYSTEM = """You are Shelfmate, a book assistant for a reader in India.
Always use tools for prices. Never guess a price.
Show prices in rupees with the store name and link."""

llm = ChatOllama(model="qwen2.5:7b", temperature=0)
agent = create_react_agent(
    llm,
    tools=[recommend_books, find_cheapest_prices, find_audiobook, log_finished_book],
    prompt=SYSTEM,
)


def ask(question: str) -> dict:
    new_run("chat")
    log.info("Question received", extra={"chars": len(question)})
    log.debug("Question text", extra={"question": question})
    with timed(log, "agent answer"):
        result = agent.invoke({"messages": [("user", question)]})
    tools = [
        c["name"]
        for m in result["messages"]
        for c in getattr(m, "tool_calls", None) or []
    ]
    log.info(
        "Answered using %d tool call(s)",
        len(tools),
        extra={"tools": tools, "steps": len(result["messages"])},
    )
    log.debug("Answer text", extra={"answer": result["messages"][-1].content})
    return result


if __name__ == "__main__":
    setup_logging("agent")
    for m in ask("I finished Golden Son, 5 stars. What next?")["messages"]:
        m.pretty_print()
