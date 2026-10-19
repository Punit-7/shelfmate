import logging

import httpx
import streamlit as st

from shelfmate.config import settings
from shelfmate.cover_card import cover_card
from shelfmate.logging_setup import setup_logging

API = settings.api_url
log = logging.getLogger("shelfmate.web")


@st.cache_resource
def start_logging() -> bool:
    setup_logging("web")
    return True


start_logging()


def call_api(method: str, path: str, **kwargs):
    """Calls the API. On failure, logs the error, shows a clear message and returns None."""
    try:
        r = httpx.request(method, f"{API}{path}", timeout=30, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        rid = e.response.headers.get("X-Request-ID", "-")
        log.error(
            "API returned %d for %s %s",
            e.response.status_code,
            method,
            path,
            extra={
                "api_path": path,
                "status": e.response.status_code,
                "request_id": rid,
            },
        )
        try:
            detail = e.response.json().get("detail", "")
        except ValueError:  # a crash returns plain text, not JSON
            detail = ""
        st.error(f"The API returned an error. {detail} (Request ID: {rid})")
    except httpx.RequestError as e:
        log.error("API not reachable", extra={"api_path": path, "error": str(e)})
        st.error("The API is not running. Start it with uvicorn and refresh this page.")
    return None


def done(message: str) -> None:
    """Shows the message after the page reloads with the new data."""
    st.session_state["flash"] = message
    st.rerun()


def cover(book: dict, width: int) -> None:
    # A book with no cover picture gets a card with its title, so no cover is blank.
    st.image(book.get("cover_url") or cover_card(book["title"]), width=width)


def remove_button(book: dict) -> None:
    """Takes the book off your shelves, after a confirmation."""
    with st.popover("Remove"):
        st.write(f"Remove {book['title']} from your shelves?")
        if st.button("Yes, remove", key=f"d{book['book_id']}") and call_api(
            "DELETE", f"/shelf/{book['book_id']}"
        ):
            done(f"Removed {book['title']}.")


def grid(books: list[dict], actions) -> None:
    """Four books per row: cover, title and author, then whatever `actions` adds."""
    if not books:
        st.caption("No books on this shelf yet.")
    cols = st.columns(4)
    for i, book in enumerate(books):
        with cols[i % 4]:
            cover(book, 160)
            st.markdown(f"**{book['title']}**  \n{book['author']}")
            actions(book)
            remove_button(book)


def reading_actions(book: dict) -> None:
    key = book["book_id"]
    chapter, total = book["chapter"], book["total_chapters"]
    if total:
        st.progress(min(chapter / total, 1.0), text=f"Chapter {chapter} of {total}")
    else:
        st.caption(f"Chapter {chapter} (total not set)")
    with st.form(f"chapters{key}", border=False):
        left, right = st.columns(2)
        new_chapter = left.number_input("Chapter", 0, 10_000, chapter)
        new_total = right.number_input(
            "Total chapters", 0, 10_000, total or 0, help="0 means not set"
        )
        if st.form_submit_button("Save progress"):
            if new_total and new_chapter > new_total:
                st.error("The chapter cannot be past the last chapter.")
            elif call_api(
                "PATCH",
                f"/shelf/{key}/progress",
                json={"chapter": new_chapter, "total_chapters": new_total or None},
            ):
                done("Progress saved.")
    rating = st.select_slider("Rating", options=[1, 2, 3, 4, 5], value=4, key=f"r{key}")
    if st.button("Finished", key=f"f{key}"):
        result = call_api("POST", f"/shelf/{key}/finish", json={"rating": rating})
        log.info("Finished clicked", extra={"book_id": key, "rating": rating})
        if result:
            done("Saved. Your new recommendations are on the way.")


def read_actions(book: dict) -> None:
    st.caption("★" * book["rating"] if book["rating"] else "Not rated")


def want_actions(book: dict) -> None:
    if st.button("Start reading", key=f"s{book['book_id']}") and call_api(
        "POST", f"/shelf/{book['book_id']}/start"
    ):
        done(f"Started {book['title']}.")


st.set_page_config(page_title="Shelfmate", page_icon="📚", layout="wide")
st.title("Shelfmate")
if message := st.session_state.pop("flash", None):
    st.success(message)

with st.sidebar:
    st.header("Add a book")
    query = st.text_input("Search Open Library")
    if len(query) >= 2:
        results = call_api("GET", "/search", params={"q": query}) or []
        labels = [
            f"{r['title']} by {r['author']} ({r['year'] or '?'})" for r in results
        ]
        pick = st.selectbox("Book", range(len(results)), format_func=labels.__getitem__)
        shelf = st.radio("Shelf", ["to-read", "currently-reading"], horizontal=True)
        if (
            pick is not None
            and st.button("Add to shelf")
            and call_api("POST", "/shelf", json={**results[pick], "shelf": shelf})
        ):
            done(f"Added {results[pick]['title']}.")

    st.header("Import from Goodreads")
    export = st.file_uploader("Goodreads library export (CSV)", type="csv")
    if export and st.button("Import"):
        result = call_api(
            "POST",
            "/import/goodreads",
            files={"file": (export.name, export.getvalue(), "text/csv")},
        )
        if result:
            st.write(
                f"Imported {result['imported']}, already on a shelf "
                f"{result['already_on_shelf']}, not found {len(result['unmatched'])}."
            )

reading, read, want, recs = st.tabs(
    ["Currently Reading", "Read", "Want to Read", "Recommendations"]
)

with reading:
    grid(
        call_api("GET", "/shelf", params={"name": "currently-reading"}) or [],
        reading_actions,
    )

with read:
    grid(call_api("GET", "/shelf", params={"name": "read"}) or [], read_actions)

with want:
    grid(call_api("GET", "/shelf", params={"name": "to-read"}) or [], want_actions)

with recs:
    data = call_api("GET", "/recommendations") or {}
    if not any(data.values()):
        st.caption("Finish a book to get recommendations.")
    for lane, label in [("continue", "Continue your series"), ("new", "Something new")]:
        if not data.get(lane):
            continue
        st.subheader(label)
        for book in data[lane]:
            left, right = st.columns([1, 4])
            with left:
                cover(book, 120)
            with right:
                st.markdown(f"**{book['title']}**  \n{book['author']}")
                if book["summary"]:
                    st.write(book["summary"])
                if book["summary_source"] == "llm":
                    st.caption(
                        "Summary written by a local AI model from the Open Library description."
                    )
                st.caption(book["because"])
                if book["shops"]:
                    st.markdown(
                        "Find it: "
                        + " · ".join(
                            f"[{s['store']}]({s['url']})" for s in book["shops"]
                        )
                    )
                else:
                    st.caption("Not listed at the stores we check.")
