import pytest
from pydantic import ValidationError

from shelfmate.agent import search
from shelfmate.agent.search import (
    format_of,
    in_stock,
    is_this_book,
    on_store,
    selling_price,
    shows_book,
    store_links,
)
from shelfmate.api.main import ProgressRequest


def test_selling_price_skips_mrp_and_discounts():
    assert selling_price("M.R.P.: ₹599 ₹349 (42% off)") == "349"
    assert selling_price("Save ₹250, now ₹349") == "349"
    assert selling_price("₹250 off today, Rs. 1,299.00") == "1,299.00"
    assert selling_price("Paperback. ₹495.00 with 38 percent savings") == "495.00"
    assert selling_price("no price here") is None


def test_on_store_checks_the_host():
    assert on_store("https://www.amazon.in/dp/1", "amazon.in")
    assert on_store("https://amazon.in/x", "amazon.in")
    assert not on_store("https://notamazon.in/x", "amazon.in")
    assert not on_store("https://blog.com/amazon.in", "amazon.in")


def test_is_this_book_rejects_other_books_and_bundles():
    me = ("Hopeless", "Colleen Hoover")
    ok = "Hopeless (English, Paperback, Hoover Colleen)"
    assert is_this_book(ok, "Hopeless (English, Paperback)", *me)
    other_author = "Hopeless: 5 (Chestnut Springs) : Silver, Elsie"
    assert not is_this_book(other_author, other_author, *me)
    box = "Hopeless Series By Colleen Hoover 5 Books Collection Set"
    assert not is_this_book(box, box, *me)
    # A Golden Son page whose description mentions Morning Star is not Morning Star.
    desc = "Golden Son by Pierce Brown. Sequel to Red Rising, before Morning Star"
    assert not is_this_book(
        desc, "Golden Son /golden-son/p/itm1", "Morning Star", "Pierce Brown"
    )


def test_format_of_needs_exactly_one_format():
    both = ("paperback", "hardcover")
    assert format_of("Hopeless (English, Paperback)", both) == "paperback"
    assert format_of("Other formats: Hardcover, Paperback", both) is None
    assert format_of("Buy Hopeless", both) is None
    assert format_of("Buy Hopeless", ("audiobook",)) == "audiobook"


def test_progress_chapter_must_fit_the_book():
    ProgressRequest(chapter=5, total_chapters=40)
    ProgressRequest(chapter=5)  # total not known yet
    with pytest.raises(ValidationError):
        ProgressRequest(chapter=41, total_chapters=40)
    with pytest.raises(ValidationError):
        ProgressRequest(chapter=-1)


def test_store_links_leave_out_series_and_second_author():
    links = store_links(
        "Golden Son (Red Rising, #2)", "Pierce Brown, Jr.", ["flipkart.com"]
    )
    assert links == [
        {
            "store": "flipkart.com",
            "url": "https://www.flipkart.com/search?q=Golden+Son+Pierce+Brown",
        }
    ]


def test_shows_book_ignores_the_search_echo():
    echo = "<title>Store : The Martian Andy Weir</title><input value='The Martian Andy Weir'>"
    other = echo + "<h2>Dune</h2><p>by Frank Herbert</p>"
    listed = echo + "<h2>The Martian</h2><p>by Andy Weir</p>"
    assert not shows_book(echo, "The Martian", "Andy Weir")
    assert not shows_book(other, "The Martian", "Andy Weir")
    assert shows_book(listed, "The Martian", "Andy Weir")


def test_in_stock_keeps_the_link_when_the_store_blocks_us(monkeypatch):
    class Blocked:
        text = "robot check"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(search.httpx, "get", lambda *a, **k: Blocked())
    assert in_stock("amazon.in", "A Blocked Test Book", "Nobody Here")
