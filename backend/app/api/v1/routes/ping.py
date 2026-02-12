from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

router = APIRouter()


@router.get("/ping", tags=["Health"])
async def ping(db: AsyncSession = Depends(get_db_session)):
    """Health check endpoint with database connection test."""
    # Example of an async database  operation
    result = await db.execute(text("SELECT version()"))
    db_version = result.scalar()

    return {
        "message": "pongi",
        "database": "connected",
        "postgres_version": db_version.split(",")[0] if db_version else "unknown",
    }
