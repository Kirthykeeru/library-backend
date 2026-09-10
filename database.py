import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./library.db")

# check_same_thread=False is an SQLite-specific quirk: by default SQLite
# only allows the thread that created a connection to use it. FastAPI can
# handle a request in a different thread than the one that opened the
# connection, so we relax that restriction here. Other databases (e.g.
# Postgres, used in most free hosting deployments) don't need this.
connect_args = {"check_same_thread": False} if SQLALCHEMY_DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# FastAPI dependency: yields one DB session per request, and guarantees
# it's closed afterwards even if the request raises an exception.
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
