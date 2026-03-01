"""Async SQLite database engine."""

from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "notes2latex.db"

engine = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}", echo=False)


async def init_db() -> None:
    """Create tables if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncSession:  # type: ignore[misc]
    """Create a new async session."""
    async with AsyncSession(engine) as session:
        yield session  # type: ignore[misc]
