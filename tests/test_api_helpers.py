from datetime import date

from shelfmate.api.main import common_genres, fill_months, split_genres


def test_genres_are_split_trimmed_and_lowercased():
    assert split_genres("Science-Fiction,  Dystopian ,") == [
        "science-fiction",
        "dystopian",
    ]
    assert split_genres(None) == []
    assert split_genres("") == []


def test_common_genres_puts_the_most_common_first():
    books = [
        {"genres": "fantasy, young-adult"},
        {"genres": "fantasy"},
        {"genres": "science-fiction, young-adult"},
        {"genres": None},
    ]
    assert common_genres(books) == ["fantasy", "young-adult", "science-fiction"]


def test_months_run_oldest_first_and_zero_fill_across_a_year_end():
    months = fill_months({"2026-01": 2, "2025-12": 1}, date(2026, 2, 10), n=4)
    assert months == [
        {"month": "2025-11", "count": 0},
        {"month": "2025-12", "count": 1},
        {"month": "2026-01", "count": 2},
        {"month": "2026-02", "count": 0},
    ]
