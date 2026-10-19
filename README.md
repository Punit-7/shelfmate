# Shelfmate

Shelfmate recommends your next book after you finish one, explains why, and links to stores that stock it.

## Architecture

```
Streamlit website --> FastAPI --> Postgres + pgvector
                         |  \--> LangGraph agent --> SearXNG (store search), Ollama (LLM)
Weekly worker ----------/
```

The API, website and worker run from one Docker image. Recommendations combine an ALS collaborative model with
embedding similarity on book text (title, description, genres).

## Results

Hidden-book test on 2,000 readers (`scripts/evaluate.py`, logged to MLflow):

| Model      | precision@5 | recall@5 |
|------------|-------------|----------|
| Popularity | 0.100       | 0.034    |
| ALS        | 0.293       | 0.098    |

Summaries are checked against the book description; `scripts/summary_report.py` prints the grounding pass rate.

## Run it locally

Needs Docker, [uv](https://docs.astral.sh/uv/) and [Ollama](https://ollama.com) running on the host.

```powershell
git clone https://github.com/Punit-7/shelfmate.git
cd shelfmate
Copy-Item .env.example .env                                    # set DB_PASSWORD, email settings
Copy-Item searxng/settings.example.yml searxng/settings.yml    # set a real secret_key
docker compose up -d db search

uv sync
uv run python scripts/download_data.py
uv run alembic upgrade head
uv run python -m shelfmate.data.load_books
uv run python -m shelfmate.data.load_ratings
uv run python -m shelfmate.data.load_genres
uv run python -m shelfmate.recommender.embed_books

docker compose up -d --build
```

Website: http://localhost:8501 · API docs: http://localhost:8000/docs · `docker compose ps` shows the API as healthy.
Logs are JSON in `logs/`; `uv run python scripts/log_report.py` summarises them.

## Limits and next steps

- Price coverage is low: shops block automated search, so the app shows store links, not prices.
- The dataset (goodbooks-10k) stops around 2017.
- ALS retrains on every start (about a minute).
- Next.js website is planned.
