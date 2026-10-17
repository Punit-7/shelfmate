import pandas as pd
from pytest import approx

from shelfmate.recommender.hybrid import hybrid, minmax
from shelfmate.recommender.lanes import next_in_series, parse_series, something_new


def test_minmax():
    assert minmax({1: 0.2, 2: 0.5, 3: 0.8}) == approx({1: 0.0, 2: 0.5, 3: 1.0})
    assert minmax({}) == {}
    assert minmax({1: 0.4, 2: 0.4}) == {1: 0.0, 2: 0.0}


def test_hybrid_cold_start_favours_content():
    top = hybrid({1: 1.0, 2: 0.0}, {1: 0.0, 2: 1.0}, n_rated=1, n=1)
    assert top[0][0] == 2
    assert hybrid({}, {}, n_rated=0) == []


def test_parse_series():
    assert parse_series("Golden Son (Red Rising, #2)") == ("Red Rising", 2.0)
    assert parse_series("The Martian") == (None, None)


BOOKS = pd.DataFrame(
    {
        "title": ["RR1", "RR2", "RR2.5", "RR3", "Ender", "Solo"],
        "author": ["Brown"] * 4 + ["Card", "Weir"],
        "series_name": ["Red Rising"] * 4 + ["Ender", None],
        "series_pos": [1, 2, 2.5, 3, 1, None],
    },
    index=[0, 1, 2, 3, 4, 5],
)


def test_next_in_series_skips_novellas():
    read = BOOKS.iloc[:2].assign(rating=[5, 4])
    assert next_in_series(read, BOOKS) == ["RR3"]


def test_next_in_series_stops_on_low_rating():
    assert next_in_series(BOOKS.iloc[:1].assign(rating=[2]), BOOKS) == []


def test_something_new_skips_started_series_and_uses_book_one():
    ranked = [(3, 0.9), (4, 0.8), (5, 0.7)]
    picks = something_new(
        ranked, BOOKS, started={"Red Rising"}, first_book={"Ender": 4}
    )
    assert [b for b, _ in picks] == [4, 5]
