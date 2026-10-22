# Shelfmate

Shelfmate recommends your next book after you finish one, explains why, and links to stores that stock it.

## Demo

<!-- TODO: record a GIF of finishing a book and getting recommendations, save as docs/demo.gif, then use ![Demo](docs/demo.gif) -->

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

## Tech stack

| Part | Tool |
|------|------|
| API | FastAPI, uvicorn |
| Website | Streamlit (first version) and Next.js in `site/` (port 3000) |
| Database | Postgres + pgvector, SQLAlchemy, Alembic |
| Recommender | implicit (ALS), sentence-transformers (embeddings) |
| Agent and LLM | LangGraph, Ollama |
| Store search | SearXNG |
| Weekly flow | Prefect |
| Experiments | MLflow |
| Tooling | uv, ruff, pytest, pre-commit, GitHub Actions, Docker Compose |

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

Streamlit website: http://localhost:8501 · Next.js site: http://localhost:3000 · API docs: http://localhost:8000/docs · `docker compose ps` shows the API and site as healthy.

Browser tests for the Next.js site (they change real data and put it back): `cd site && PW_CHANNEL=msedge npm run test:e2e`, with the stack running. Without Edge, run `npx playwright install chromium` once and leave `PW_CHANNEL` unset.
Logs are JSON in `logs/`; `uv run python scripts/log_report.py` summarises them.

## Limits and next steps

- Price coverage is low: shops block automated search, so the app shows store links, not prices.
- The dataset (goodbooks-10k) stops around 2017.
- ALS retrains on every start (about a minute).
- The Next.js site (`site/`) has the shelves, recommendations, add-book and dashboard pages. Streamlit is still the first version and will be removed once the Next.js site covers everything.
