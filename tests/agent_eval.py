from ollama import ResponseError

from shelfmate.agent.graph import agent

CASES = [
    {"ask": "What should I read next?", "tools": ["recommend_books"]},
    {"ask": "Recommend me 3 books", "tools": ["recommend_books"]},
    {"ask": "Suggest something like Red Rising", "tools": ["recommend_books"]},
    {"ask": "I need a new fantasy series, any ideas?", "tools": ["recommend_books"]},
    {"ask": "Give me 10 recommendations", "tools": ["recommend_books"]},
    {"ask": "What would you pick for me this weekend?", "tools": ["recommend_books"]},
    {"ask": "Anything good I haven't read yet?", "tools": ["recommend_books"]},
    {"ask": "Show me my top picks", "tools": ["recommend_books"]},
    {"ask": "Cheapest paperback of Dune?", "tools": ["find_cheapest_prices"]},
    {
        "ask": "How much is The Way of Kings in hardcover?",
        "tools": ["find_cheapest_prices"],
    },
    {"ask": "Where can I buy Mistborn cheapest?", "tools": ["find_cheapest_prices"]},
    {"ask": "Price of Ender's Game, used is fine", "tools": ["find_cheapest_prices"]},
    {"ask": "Find me the best deal on The Martian", "tools": ["find_cheapest_prices"]},
    {
        "ask": "Is Golden Son cheaper on Flipkart or Amazon?",
        "tools": ["find_cheapest_prices"],
    },
    {
        "ask": "What does a new copy of Project Hail Mary cost in India?",
        "tools": ["find_cheapest_prices"],
    },
    {
        "ask": "Lowest price for a second-hand Hunger Games?",
        "tools": ["find_cheapest_prices"],
    },
    {"ask": "Is Morning Star on Audible?", "tools": ["find_audiobook"]},
    {"ask": "Is there an audiobook of Dune?", "tools": ["find_audiobook"]},
    {
        "ask": "Can I listen to The Name of the Wind on Google Play Books?",
        "tools": ["find_audiobook"],
    },
    {"ask": "Find the audiobook for Project Hail Mary", "tools": ["find_audiobook"]},
    {"ask": "Does Audible India have Red Rising?", "tools": ["find_audiobook"]},
    {
        "ask": "I'd rather listen than read Mistborn, is it available?",
        "tools": ["find_audiobook"],
    },
    {"ask": "Audiobook version of Ender's Game?", "tools": ["find_audiobook"]},
    {"ask": "I finished Dune, 4 stars", "tools": ["log_finished_book"]},
    {"ask": "Just read The Martian, loved it, 5 stars", "tools": ["log_finished_book"]},
    {"ask": "Mark Mistborn as finished with a 3", "tools": ["log_finished_book"]},
    {
        "ask": "I finished Golden Son, 5 stars",
        "tools": ["log_finished_book", "recommend_books"],
    },
    {
        "ask": "Finished Ender's Game, 4 stars. What next?",
        "tools": ["log_finished_book", "recommend_books"],
    },
    {
        "ask": "Cheapest paperback of Dune, and is there an audiobook too?",
        "tools": ["find_cheapest_prices", "find_audiobook"],
    },
    {
        "ask": "I read Morning Star, 5 stars. Is the next book on Audible?",
        "tools": ["log_finished_book", "find_audiobook"],
    },
]


def tools_called(result) -> list[str]:
    return [
        c["name"]
        for m in result["messages"]
        for c in getattr(m, "tool_calls", None) or []
    ]


correct = 0
for case in CASES:
    try:
        result = agent.invoke({"messages": [("user", case["ask"])]})
    except ResponseError as e:  # one bad model reply should not stop the whole run
        print("ERROR:", case["ask"], "->", str(e).splitlines()[0])
        continue
    called = tools_called(result)
    if all(t in called for t in case["tools"]):
        correct += 1
    else:
        print("MISS:", case["ask"], "->", called)

print(f"Tool accuracy: {correct}/{len(CASES)} = {correct / len(CASES):.0%}")
