from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
import os
from dotenv import load_dotenv

load_dotenv()
# 1. Define your Database URL
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DATABASE_URL = f"postgresql+asyncpg://postgres:{POSTGRES_PASSWORD}@localhost:5432/postgres"

# 2. Create the SQLAlchemy async engine
engine = create_async_engine(DATABASE_URL, echo=True)

# 3. Create a session maker
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)

# 4. Create a Base class
Base = declarative_base()