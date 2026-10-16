"""Evaluate the ALS model against a popularity baseline.

Hide 20% of each test reader's liked books, train on the rest, and count how
many hidden books appear in the top 5 recommendations.

Run from the project root:  uv run python scripts/evaluate.py
"""

import logging

import mlflow
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from sqlalchemy import create_engine

from shelfmate.config import settings
from shelfmate.logging_setup import new_run, setup_logging, timed
from shelfmate.recommender.collaborative import train

log = logging.getLogger("shelfmate.scripts.evaluate")

TEST_USERS = 2000
MIN_LIKED = 20
HIDE_SHARE = 0.2
K = 5
PARAMS = {"factors": 64, "regularization": 0.05, "iterations": 20}
SEED = 42


def load_liked() -> pd.DataFrame:
    engine = create_engine(settings.database_url)
    ratings = pd.read_sql("SELECT user_id, book_id, rating FROM ratings", engine)
    # The loader was run twice, so the table has duplicate pairs. Keep one of each.
    ratings = ratings.drop_duplicates(["user_id", "book_id"])
    return ratings[ratings["rating"] >= 4]


def split(liked: pd.DataFrame, rng: np.random.Generator):
    """Pick test readers, hide part of their liked books, and return the rest as training data."""
    per_user = liked.groupby("user_id")["book_id"].apply(list)
    eligible = per_user[per_user.apply(len) >= MIN_LIKED]
    test = eligible.sample(min(TEST_USERS, len(eligible)), random_state=SEED)

    hidden = {}
    for uid, books in test.items():
        books = list(books)
        rng.shuffle(books)
        hidden[uid] = set(books[: max(1, int(HIDE_SHARE * len(books)))])

    drop = pd.MultiIndex.from_tuples([(u, b) for u, hs in hidden.items() for b in hs])
    keep = ~liked.set_index(["user_id", "book_id"]).index.isin(drop)
    return liked[keep], hidden


def to_matrix(liked: pd.DataFrame, shape) -> csr_matrix:
    return csr_matrix(
        (np.ones(len(liked), dtype=np.float32), (liked["user_id"], liked["book_id"])),
        shape=shape,
    )


def score(recommend, hidden: dict) -> tuple[float, float]:
    """Return (precision@5, recall@5) averaged over the test readers."""
    precisions, recalls = [], []
    for uid, hs in hidden.items():
        hits = len(set(recommend(uid)) & hs)
        precisions.append(hits / K)
        recalls.append(hits / len(hs))
    return float(np.mean(precisions)), float(np.mean(recalls))


def log_run(name: str, precision: float, recall: float) -> None:
    with mlflow.start_run(run_name=name):
        mlflow.log_params(
            {
                "model": name,
                **PARAMS,
                "test_users": TEST_USERS,
                "hide_share": HIDE_SHARE,
            }
        )
        mlflow.log_metrics({"precision_at_5": precision, "recall_at_5": recall})


if __name__ == "__main__":
    setup_logging("evaluate")
    new_run("evaluate")
    mlflow.set_experiment("shelfmate-recommender")

    rng = np.random.default_rng(SEED)
    liked = load_liked()
    train_liked, hidden = split(liked, rng)
    shape = (int(liked["user_id"].max()) + 1, int(liked["book_id"].max()) + 1)
    train_matrix = to_matrix(train_liked, shape)
    log.info(
        "Split ready",
        extra={
            "test_users": len(hidden),
            "hidden_books": sum(len(h) for h in hidden.values()),
        },
    )

    with timed(log, "ALS training for evaluation", **PARAMS):
        model = train(train_matrix, **PARAMS)

    def als_recommend(uid):
        ids, _ = model.recommend(
            uid, train_matrix[uid], N=K, filter_already_liked_items=True
        )
        return list(ids)

    popular = np.asarray(train_matrix.sum(axis=0)).ravel().argsort()[::-1]

    def popularity_recommend(uid):
        seen = set(train_matrix[uid].indices)
        return [b for b in popular if b not in seen][:K]

    with timed(log, "scoring"):
        als_p, als_r = score(als_recommend, hidden)
        pop_p, pop_r = score(popularity_recommend, hidden)

    log_run("als-64-factors", als_p, als_r)
    log_run("popularity-baseline", pop_p, pop_r)
    log.info(
        "Evaluation finished",
        extra={
            "als_precision": als_p,
            "als_recall": als_r,
            "pop_precision": pop_p,
            "pop_recall": pop_r,
        },
    )
    print(f"ALS precision@5 of {als_p:.3f} vs popularity baseline of {pop_p:.3f}")
    print(f"ALS recall@5    of {als_r:.3f} vs popularity baseline of {pop_r:.3f}")
