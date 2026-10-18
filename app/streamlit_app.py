import logging

import httpx
import streamlit as st

from shelfmate.logging_setup import setup_logging

API = "http://localhost:8000"
COVER = "https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg"
log = logging.getLogger("shelfmate.web")


@st.cache_resource
def start_logging() -> bool:
    setup_logging("web")
    return True


start_logging()


def api_get(path: str, **params):
    """Calls the API. On failure, logs the error and shows a clear message on the page."""
    try:
        r = httpx.get(f"{API}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        rid = e.response.headers.get("X-Request-ID", "-")
        log.error(
            "API returned %d for %s",
            e.response.status_code,
            path,
            extra={
                "api_path": path,
                "status": e.response.status_code,
                "request_id": rid,
            },
        )
        st.error(f"The API returned an error. Request ID: {rid}")
    except httpx.RequestError as e:
        log.error("API not reachable", extra={"api_path": path, "error": str(e)})
        st.error("The API is not running. Start it with uvicorn and refresh this page.")
    return []


st.set_page_config(page_title="Shelfmate", page_icon="📚", layout="wide")
st.title("Shelfmate")

reading, read, want, recs = st.tabs(
    ["Currently Reading", "Read", "Want to Read", "Recommendations"]
)

with reading:
    books = api_get("/shelf", name="currently-reading")
    cols = st.columns(4)
    for i, book in enumerate(books):
        with cols[i % 4]:
            if book["isbn13"]:
                st.image(COVER.format(isbn=book["isbn13"]), width=160)
            st.markdown(f"**{book['title']}**  \n{book['author']}")
            st.progress(book["progress_pct"] / 100)
            rating = st.select_slider(
                "Rating", options=[1, 2, 3, 4, 5], value=4, key=f"r{book['book_id']}"
            )
            if st.button("Finished", key=f"f{book['book_id']}"):
                r = httpx.post(
                    f"{API}/shelf/{book['book_id']}/finish", json={"rating": rating}
                )
                log.info(
                    "Finished clicked",
                    extra={
                        "book_id": book["book_id"],
                        "rating": rating,
                        "status": r.status_code,
                    },
                )
                st.success("Saved. Your new recommendations are on the way.")
