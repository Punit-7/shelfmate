import io

import pytest

from shelfmate.data.import_goodreads import find_book, import_goodreads

INDEX = {
    "red rising (red rising, #1)": [(858, "pierce brown")],
    "red rising": [(858, "pierce brown")],
    "tom jones": [(1, "henry fielding, thomas keymer"), (2, "someone else")],
}


def test_find_book_matches_title_and_author():
    assert find_book("Red Rising (Red Rising, #1)", "Pierce Brown", INDEX) == 858
    assert find_book("Red Rising", "Pierce  Brown", INDEX) == 858  # no series suffix
    assert find_book("Tom Jones", "Henry Fielding", INDEX) == 1  # first author only
    assert find_book("Tom Jones", "Nobody", INDEX) is None
    assert find_book("Red Rising", "", INDEX) is None
    assert find_book("Unknown", "Pierce Brown", INDEX) is None


def test_import_rejects_files_that_are_not_goodreads_exports():
    with pytest.raises(ValueError, match="missing"):
        import_goodreads(io.StringIO("Title,Author\nDune,Frank Herbert\n"), None)
    with pytest.raises(ValueError, match="readable"):
        import_goodreads(io.StringIO(""), None)
