from shelfmate.api.main import page_lanes


def books(n_continue, n_new):
    return [{"lane": "continue", "book_id": i} for i in range(n_continue)] + [
        {"lane": "new", "book_id": 100 + i} for i in range(n_new)
    ]


def test_each_lane_gets_its_own_page_and_totals_count_everything():
    page, total = page_lanes(books(2, 12), offset=5, limit=5, lane=None)
    assert [b["book_id"] for b in page["new"]] == [105, 106, 107, 108, 109]
    assert page["continue"] == []  # only 2 continue books, so offset 5 is past them
    assert total == {"continue": 2, "new": 12}


def test_asking_for_one_lane_leaves_the_other_empty():
    page, _ = page_lanes(books(3, 12), offset=0, limit=5, lane="new")
    assert len(page["new"]) == 5 and page["continue"] == []


def test_the_last_page_is_short():
    page, total = page_lanes(books(0, 7), offset=5, limit=5, lane="new")
    assert [b["book_id"] for b in page["new"]] == [105, 106]
    assert total["new"] == 7
