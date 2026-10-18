import pandas as pd
from sqlalchemy import create_engine

from shelfmate.config import settings

books = pd.read_sql(
    "SELECT summary_source FROM books WHERE summary IS NOT NULL",
    create_engine(settings.database_url),
)
if books.empty:
    raise SystemExit("No summaries saved yet, so there is nothing to report.")
print(books["summary_source"].value_counts(normalize=True).round(2).to_string(), "\n")

logs = pd.read_json("logs/loader.jsonl", lines=True)
accepted = (logs["message"] == "LLM summary accepted").sum()
rejected = (logs["message"] == "LLM summary rejected, using description").sum()
checked = accepted + rejected
print(
    f"Grounding pass rate: {accepted}/{checked} = {accepted / checked:.0%}"
    if checked
    else "No LLM summaries were checked."
)
