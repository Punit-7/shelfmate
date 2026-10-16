from pathlib import Path

import httpx

BASE = "https://raw.githubusercontent.com/zygmuntz/goodbooks-10k/master"
FILES = ["books.csv", "ratings.csv"]
RAW = Path("data/raw")


def download(name: str) -> None:
    target = RAW / name
    if target.exists():
        print(f"skip  {name} (already downloaded)")
        return
    part = target.with_name(name + ".part")
    with httpx.stream("GET", f"{BASE}/{name}", timeout=60, follow_redirects=True) as r:
        r.raise_for_status()
        with part.open("wb") as f:
            for chunk in r.iter_bytes(1_048_576):
                f.write(chunk)
    part.rename(target)
    print(f"done  {name} ({target.stat().st_size / 1_000_000:.1f} MB)")


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        download(name)
