from shelfmate.cover_card import cover_card
from shelfmate.data import openlibrary


def fake_work(monkeypatch, covers, loads):
    entries = [{"languages": [{"key": "/languages/eng"}], "covers": covers}]
    monkeypatch.setattr(openlibrary, "_get", lambda *a, **k: {"entries": entries})
    monkeypatch.setattr(openlibrary, "cover_loads", lambda url: url in loads)


def test_english_cover_skips_the_placeholder_and_dead_pictures(monkeypatch):
    # -1 is Open Library's "no cover", 111 is a picture that is gone, 368831 works.
    good = openlibrary.COVER.format(id=368831)
    fake_work(monkeypatch, [-1, 111, 368831], {good})
    assert openlibrary.english_cover("/works/OL1W") == good


def test_english_cover_is_none_when_no_picture_loads(monkeypatch):
    fake_work(monkeypatch, [-1, 111], set())
    assert openlibrary.english_cover("/works/OL1W") is None


def test_cover_card_wraps_and_escapes_the_title():
    card = cover_card("Sundiver <b> (The Uplift Saga, #1)")
    assert card.startswith("<svg") and "&lt;b&gt;" in card
    assert "Uplift" not in card  # the series part is left out
