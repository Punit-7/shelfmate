import numpy as np

FALLBACK = "Popular with readers who share your taste"


def because_you_liked(
    rec_emb: np.ndarray | None, liked: dict[str, np.ndarray], min_sim: float = 0.3
) -> str:
    """Names the liked book whose embedding is closest to the recommended book."""
    if rec_emb is None or not liked:
        return FALLBACK
    titles = list(liked)
    sims = np.array([float(rec_emb @ liked[t]) for t in titles])
    best = int(sims.argmax())
    if sims[best] < min_sim:
        return FALLBACK
    return f"Because you liked {titles[best]} (similarity {sims[best]:.2f})"


if __name__ == "__main__":
    liked = {
        "Red Rising": np.array([0.8, 0.6, 0.0]),
        "The Martian": np.array([0.0, 0.6, 0.8]),
    }
    print(because_you_liked(np.array([0.6, 0.8, 0.0]), liked))
    print(because_you_liked(np.array([0.0, 0.0, 0.2]), liked))
