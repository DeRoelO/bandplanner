from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool
from app.config import settings

# SQLite specifieke connectie argumenten om multi-threading toe te staan
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}

# For SQLite we use NullPool (no connection pooling) since SQLite is file-based and pooling
# causes QueuePool exhaustion when many background tasks run concurrently.
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        poolclass=NullPool,
        echo=False
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args=connect_args,
        pool_size=10,
        max_overflow=20,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
