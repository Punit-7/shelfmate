import logging

from sentence_transformers import SentenceTransformer

from shelfmate.logging_setup import new_run, setup_logging, timed

log = logging.getLogger(__name__)
MODEL_NAME = "all-MiniLM-L6-v2"
model = SentenceTransformer(MODEL_NAME)


def embed(texts: list[str]):
    with timed(log, "embedding", texts=len(texts), model_name=MODEL_NAME):
        return model.encode(texts, normalize_embeddings=True)


if __name__ == "__main__":
    setup_logging("recommender")
    new_run("embed")
    texts = [
        "Red Rising. A low-caste miner infiltrates the ruling elite on Mars to destroy it.",
        "Ender's Game. A gifted child is trained at a military school in space to fight an alien war.",
        "Pride and Prejudice. A young woman navigates marriage and class in rural England.",
    ]
    emb = embed(texts)
    print(emb.shape)
    print(emb @ emb.T)
