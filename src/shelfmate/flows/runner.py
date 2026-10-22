"""Runs the recommendation flow in the worker when the API asks for it.

The API only adds a row to pipeline_runs. Running the flow here, in the worker's one
long-lived process, means Prefect starts its temporary server once instead of inside
the API on every finished book.
"""

import logging
import time

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from shelfmate.agent.tools import engine
from shelfmate.db.models import Book, PipelineRun, Recommendation
from shelfmate.flows.pipeline import after_finished_book, fill_details
from shelfmate.logging_setup import setup_logging

log = logging.getLogger("shelfmate.flows.runner")
POLL_SECONDS = 5


def set_status(ids: list[int], status: str, **times) -> None:
    with Session(engine) as session, session.begin():
        session.execute(
            update(PipelineRun)
            .where(PipelineRun.id.in_(ids))
            .values(status=status, **times)
        )


def take_requests() -> list[int]:
    """Every queued request, now marked running. One run answers all of them."""
    with Session(engine) as session:
        ids = list(
            session.scalars(
                select(PipelineRun.id).where(PipelineRun.status == "queued")
            )
        )
    if ids:
        set_status(ids, "running", started_at=func.now())
    return ids


def missing_summaries() -> list[int]:
    """Recommended books that have no summary yet, best first."""
    with Session(engine) as session:
        return list(
            session.scalars(
                select(Recommendation.book_id)
                .join(Book, Book.id == Recommendation.book_id)
                .where(Book.summary.is_(None))
                .order_by(Recommendation.rank)
            )
        )


def write_missing_summaries(run_ids: list[int]) -> None:
    """Writes every missing summary, then closes the runs. The website says "summaries" meanwhile."""
    set_status(run_ids, "summaries")
    for book_id in missing_summaries():
        fill_details.fn(book_id)  # .fn: the plain function, no Prefect task run needed
    set_status(run_ids, "done", finished_at=func.now())


def watch_requests() -> None:
    """Runs forever: waits for a request, runs the flow, records how it went."""
    # A run cut off by a restart would look busy for ever, so close it first.
    with Session(engine) as session, session.begin():
        session.execute(
            update(PipelineRun)
            .where(PipelineRun.status.in_(["running", "summaries"]))
            .values(status="failed", finished_at=func.now())
        )
    # The restart may also have cut summary writing short. Pick it up again.
    if missing_summaries():
        with Session(engine) as session, session.begin():
            resume = PipelineRun(status="summaries")
            session.add(resume)
            session.flush()
            resume_id = resume.id
        log.info("Resuming the missing summaries")
        write_missing_summaries([resume_id])
    log.info("Waiting for recommendation requests")
    while True:
        try:
            ids = take_requests()
        except Exception:
            log.exception("Could not read pipeline_runs")
            time.sleep(POLL_SECONDS)
            continue
        if not ids:
            time.sleep(POLL_SECONDS)
            continue
        log.info("Recommendation run requested", extra={"requests": len(ids)})
        try:
            after_finished_book()
        except Exception:
            log.exception("Recommendation flow failed")
            set_status(ids, "failed", finished_at=func.now())
            continue
        # The new picks are saved. The website now says "writing summaries", not "updating".
        write_missing_summaries(ids)


if __name__ == "__main__":
    setup_logging("runner")
    watch_requests()
