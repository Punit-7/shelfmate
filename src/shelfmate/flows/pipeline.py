import logging

from prefect import flow, task

from shelfmate.logging_setup import new_run, timed

log = logging.getLogger(__name__)


@task(retries=3, retry_delay_seconds=[10, 20, 40])
def get_recommendations(
    n: int = 5,
) -> list[dict]: ...  # calls the hybrid recommender and the two lanes from Phase 2


@task(retries=3, retry_delay_seconds=[10, 20, 40])
def get_prices(book: dict) -> list[dict]:
    offers: list[
        dict
    ] = []  # fill with find_offer(...) results for each store and format
    log.info(
        "Found %d offers for %s",
        len(offers),
        book["title"],
        extra={"book_id": book["book_id"], "offers": len(offers)},
    )
    if not offers:
        log.warning("No prices found", extra={"book_id": book["book_id"]})
    return offers


@task
def save_and_email(
    results: list[dict],
) -> None: ...  # writes to the recommendations and prices tables, then sends the email


@flow(name="after-finished-book", log_prints=True)
def after_finished_book():
    new_run("flow")
    log.info("Pipeline started")
    with timed(log, "after-finished-book flow"):
        books = get_recommendations()
        if not books:
            log.warning("No recommendations, nothing to price or email")
            return
        results = [{**b, "offers": get_prices(b)} for b in books]
        save_and_email(results)
    log.info("Sent %d recommendations", len(results), extra={"books": len(results)})
