"""
FastAPI dependency injection helpers.
"""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

# Re-export as a typed dependency so routes can simply `Depends(get_session)`
async def get_session(db: AsyncSession = Depends(get_db)) -> AsyncGenerator[AsyncSession, None]:
    yield db
