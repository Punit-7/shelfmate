import time

from langchain_core.messages import AIMessage
from langchain_core.tools import tool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from shelfmate.agent.graph import LIMITS

events = []


@tool
def log_finished_book(title: str) -> str:
    """Save a book."""
    events.append("log start")
    time.sleep(0.2)  # slow enough that a parallel call would start before this ends
    events.append("log end")
    return "saved"


@tool
def recommend_books() -> str:
    """Recommend books."""
    events.append("recommend start")
    return "picks"


def test_tools_from_one_step_run_in_order():
    calls = [
        {"name": "log_finished_book", "args": {"title": "Golden Son"}, "id": "1"},
        {"name": "recommend_books", "args": {}, "id": "2"},
    ]
    # The same tools node the agent uses, alone in a graph, run with the agent's settings.
    graph = StateGraph(MessagesState)
    graph.add_node("tools", ToolNode([log_finished_book, recommend_books]))
    graph.add_edge(START, "tools")
    graph.compile().invoke({"messages": [AIMessage("", tool_calls=calls)]}, LIMITS)
    assert events == ["log start", "log end", "recommend start"]
