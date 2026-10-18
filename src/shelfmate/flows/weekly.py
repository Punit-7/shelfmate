import logging

from prefect import flow

from shelfmate.logging_setup import new_run, setup_logging

log = logging.getLogger(__name__)


@flow(name="weekly-refresh")
def weekly_refresh():
    new_run("weekly")
    log.info("Weekly refresh started")
    # 1. refresh prices for every book on Want to Read
    # 2. search Open Library for new books by authors you rated 4+
    # 3. email a summary of price drops and new releases
    log.info("Weekly refresh finished")


if __name__ == "__main__":
    setup_logging("worker")
    weekly_refresh.serve(name="sunday-9am", cron="0 9 * * 0")
