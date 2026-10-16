from sqlalchemy import create_engine, text

from shelfmate.config import settings

engine = create_engine(settings.database_url)
QUERY = "SELECT id FROM books ORDER BY embedding <=> CAST(:v AS vector) LIMIT 20"


def run(conn, seed, use_index: bool):
    conn.execute(text(f"SET enable_indexscan = {'on' if use_index else 'off'}"))
    plan = conn.execute(text("EXPLAIN ANALYZE " + QUERY), {"v": seed}).scalars().all()
    ids = conn.execute(text(QUERY), {"v": seed}).scalars().all()
    scan = next(
        line for line in plan if "Seq Scan" in line or "books_embedding_hnsw" in line
    )
    return ids, scan.split("(")[0].strip(), plan[-1]


with engine.connect() as conn:
    seed = conn.execute(text("SELECT embedding::text FROM books WHERE id = 1")).scalar()
    exact, scan_a, time_a = run(conn, seed, use_index=False)
    approx, scan_b, time_b = run(conn, seed, use_index=True)

print("Exact:", scan_a, "|", time_a)
print("HNSW: ", scan_b, "|", time_b)
print("Same books in both top 20:", len(set(exact) & set(approx)))
