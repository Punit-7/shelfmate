import re

SERIES = re.compile(r"\((?P<name>.+?),\s*#(?P<pos>[\d.]+)\)\s*$")


def parse_series(title: str):
    m = SERIES.search(title)
    if not m:
        return None, None
    return m["name"].strip(), float(m["pos"])
