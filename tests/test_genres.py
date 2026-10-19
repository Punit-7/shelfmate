import pandas as pd

from shelfmate.data.load_genres import genres_by_book
from shelfmate.recommender.embed_books import book_text


def test_genres_keep_genres_drop_shelves_and_merge_aliases():
    tags = pd.DataFrame(
        {
            "tag_id": [1, 2, 3, 4, 5],
            "tag_name": [
                "to-read",
                "sci-fi",
                "science-fiction",
                "dystopia",
                "favorites",
            ],
        }
    )
    book_tags = pd.DataFrame(
        {
            "goodreads_book_id": [10, 10, 10, 10, 10],
            "tag_id": [1, 2, 3, 4, 5],
            "count": [900, 50, 40, 30, 20],
        }
    )
    books = pd.DataFrame({"book_id": [858], "goodreads_book_id": [10]})
    # to-read and favorites are shelves; sci-fi and science-fiction are one genre.
    assert genres_by_book(tags, book_tags, books) == {858: "science-fiction, dystopian"}


def test_book_text_adds_genres_only_when_known():
    assert book_text("Red Rising", "Pierce Brown", None) == "Red Rising. Pierce Brown."
    assert (
        book_text("Red Rising", "Pierce Brown", "science-fiction")
        == "Red Rising. Pierce Brown. Genres: science-fiction."
    )
