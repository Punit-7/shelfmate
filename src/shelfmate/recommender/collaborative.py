import logging

import numpy as np
import pandas as pd
from implicit.als import AlternatingLeastSquares
from scipy.sparse import csr_matrix

from shelfmate.logging_setup import timed

log = logging.getLogger(__name__)


def build_matrix(ratings: pd.DataFrame) -> csr_matrix:
    liked = ratings[ratings["rating"] >= 4]
    n_users = ratings["user_id"].max() + 1
    n_books = ratings["book_id"].max() + 1
    matrix = csr_matrix(
        (np.ones(len(liked), dtype=np.float32), (liked["user_id"], liked["book_id"])),
        shape=(n_users, n_books),
    )
    sparsity = 1 - matrix.nnz / (n_users * n_books)
    log.info(
        "Built user x book matrix",
        extra={
            "users": int(n_users),
            "books": int(n_books),
            "liked": int(matrix.nnz),
            "sparsity": round(sparsity, 4),
        },
    )
    return matrix


def train(
    user_items: csr_matrix,
    factors: int = 64,
    regularization: float = 0.05,
    iterations: int = 20,
) -> AlternatingLeastSquares:
    params = {
        "factors": factors,
        "regularization": regularization,
        "iterations": iterations,
    }
    log.info("Training ALS", extra=params)
    model = AlternatingLeastSquares(**params)
    with timed(log, "ALS training", **params):
        model.fit(user_items)
    return model


def recommend_for_me(model, my_liked_ids: list[int], n_books: int, n: int = 5):
    if not my_liked_ids:
        log.warning("No liked books yet, collaborative filtering cannot score anything")
        return []
    me = csr_matrix(
        (
            np.ones(len(my_liked_ids), dtype=np.float32),
            ([0] * len(my_liked_ids), my_liked_ids),
        ),
        shape=(1, n_books),
    )
    ids, scores = model.recommend(0, me, N=n, recalculate_user=True)
    log.debug(
        "Collaborative scores",
        extra={
            "liked_ids": my_liked_ids,
            "top_ids": ids.tolist(),
            "top_scores": [round(float(s), 3) for s in scores],
        },
    )
    return list(zip(ids, scores))
