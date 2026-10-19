import textwrap
from html import escape


def cover_card(title: str) -> str:
    """An SVG card with the book's title, for a book that has no cover picture."""
    lines = textwrap.wrap(title.split(" (")[0], 16)[:5]
    text = "".join(
        f'<text x="80" y="{100 + 24 * i}" text-anchor="middle" font-family="serif" '
        f'font-size="17" fill="#EDE6DB">{escape(line)}</text>'
        for i, line in enumerate(lines)
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="240" viewBox="0 0 160 240">'
        '<rect width="160" height="240" fill="#2A2A2E" stroke="#C8553D" stroke-width="4"/>'
        f"{text}</svg>"
    )
