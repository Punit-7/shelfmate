import logging
from pathlib import Path

import httpx

from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger("shelfmate.scripts.download")
BASE = "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master"
FILES = ["books.csv", "ratings.csv"]
RAW = Path("data/raw")


def download(name: str) -> None:
    target = RAW / name
    if target.exists():
        log.info(
            "Skipping %s, already downloaded",
            name,
            extra={"file": name, "bytes": target.stat().st_size},
        )
        return
    url = f"{BASE}/{name}"
    log.debug("Starting download", extra={"file": name, "url": url})
    part = target.with_name(name + ".part")
    with timed(log, "download", file=name):
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            with part.open("wb") as f:
                for chunk in r.iter_bytes(1_048_576):
                    f.write(chunk)
        part.rename(target)
    size = target.stat().st_size
    log.info(
        "Saved %s (%.1f MB)",
        name,
        size / 1_000_000,
        extra={"file": name, "bytes": size},
    )


if __name__ == "__main__":
    setup_logging("download")
    new_run("download")
    RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        download(name)
