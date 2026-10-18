import logging
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, Request
from pydantic import BaseModel, Field

from shelfmate.logging_setup import run_id, setup_logging
from shelfmate.flows.pipeline import after_finished_book

setup_logging("api")
log = logging.getLogger(__name__)
app = FastAPI(title="Shelfmate API")


@app.middleware("http")
async def log_requests(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
    run_id.set(f"req-{rid}")
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        ms = round((time.perf_counter() - start) * 1000, 1)
        log.exception(
            "%s %s crashed after %.1f ms",
            request.method,
            request.url.path,
            ms,
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": ms,
            },
        )
        raise
    ms = round((time.perf_counter() - start) * 1000, 1)
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO
    log.log(
        level,
        "%s %s -> %d in %.1f ms",
        request.method,
        request.url.path,
        response.status_code,
        ms,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": ms,
        },
    )
    response.headers["X-Request-ID"] = rid
    return response


class FinishRequest(BaseModel):
    rating: int = Field(ge=1, le=5)


@app.post("/shelf/{book_id}/finish")
def finish_book(book_id: int, req: FinishRequest, background: BackgroundTasks):
    ...  # move the book to the Read shelf and save the rating
    log.info("Book finished", extra={"book_id": book_id, "rating": req.rating})
    background.add_task(after_finished_book)
    log.debug("Recommendation flow queued", extra={"book_id": book_id})
    return {"status": "saved", "book_id": book_id, "rating": req.rating}
