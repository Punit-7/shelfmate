from types import SimpleNamespace

from shelfmate.agent.graph import strip_unlisted_links


def result(tool_text):
    return {"messages": [SimpleNamespace(type="tool", content=tool_text)]}


def test_a_link_from_a_tool_is_kept():
    r = result("Search: https://www.amazon.in/s?k=red+rising")
    answer = "Try https://www.amazon.in/s?k=red+rising for it."
    assert strip_unlisted_links(answer, r) == answer


def test_a_link_the_tools_did_not_return_is_removed():
    r = result("Search: https://www.amazon.in/s?k=red+rising")
    out = strip_unlisted_links(
        "Buy it at https://www.amazon.com/Martian-Andy-Weir/dp/0062274756", r
    )
    assert out == "Buy it at [link removed]"


def test_a_full_stop_after_a_kept_link_does_not_hide_it():
    r = result("https://www.flipkart.com/x")
    assert (
        strip_unlisted_links("See https://www.flipkart.com/x.", r)
        == "See https://www.flipkart.com/x."
    )
