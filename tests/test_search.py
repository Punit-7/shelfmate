import pytest
from pydantic import ValidationError

from shelfmate.agent.search import format_of, is_this_book, on_store, selling_price
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
