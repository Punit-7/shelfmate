from sqlalchemy import create_engine, text

from shelfmate.config import settings

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    print(conn.execute(text("SELECT version()")).scalar())
