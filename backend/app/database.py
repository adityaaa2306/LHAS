from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator
import os
from dotenv import load_dotenv

load_dotenv()

# Database URL - using asyncpg driver for async PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/lhas"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "False").lower() == "true",
    future=True,
    pool_size=20,
    max_overflow=40,
)

# Session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    # Import ALL models to register them with SQLAlchemy metadata
    from app.models import Base, Mission, Session, Alert, QueryAnalysis, ResearchPaper, IngestionEvent
    from app.models.memory import MemoryEventType, SynthesisTrigger
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for event_type in MemoryEventType:
            try:
                await conn.execute(
                    text(f"ALTER TYPE memoryeventtype ADD VALUE IF NOT EXISTS '{event_type.name}'")
                )
            except Exception:
                # The enum may not exist yet on a fresh DB until after create_all, or
                # some backends may not support ALTER TYPE in the same way. In those
                # cases, create_all has already created the latest enum definition.
                pass
        for trigger_type in SynthesisTrigger:
            try:
                await conn.execute(
                    text(f"ALTER TYPE synthesistrigger ADD VALUE IF NOT EXISTS '{trigger_type.name}'")
                )
            except Exception:
                pass
        try:
            await conn.execute(
                text(
                    "ALTER TABLE missions "
                    "ADD COLUMN IF NOT EXISTS contradiction_asymmetry_threshold DOUBLE PRECISION "
                    "DEFAULT 0.35 NOT NULL"
                )
            )
        except Exception:
            pass
        mission_alters = [
            "ALTER TABLE missions ADD COLUMN IF NOT EXISTS benchmark_text TEXT",
            "ALTER TABLE missions ADD COLUMN IF NOT EXISTS benchmark_source VARCHAR(255)",
        ]
        for statement in mission_alters:
            try:
                await conn.execute(text(statement))
            except Exception:
                pass
        synthesis_history_alters = [
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS confidence_tier VARCHAR(16)",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS dominant_direction VARCHAR(32)",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS claim_ids_tier1 JSON DEFAULT '[]'::json NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS claim_ids_tier2 JSON DEFAULT '[]'::json NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS claim_ids_tier3 JSON DEFAULT '[]'::json NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS contradictions_included JSON DEFAULT '[]'::json NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS change_magnitude VARCHAR(16)",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS confidence_delta DOUBLE PRECISION",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS direction_changed BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS prior_synthesis_id UUID",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS llm_call_id UUID",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS validation_passed BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS llm_fallback BOOLEAN DEFAULT FALSE NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS word_count INTEGER DEFAULT 0 NOT NULL",
            "ALTER TABLE memory_synthesis_history ADD COLUMN IF NOT EXISTS evidence_package JSON",
        ]
        for statement in synthesis_history_alters:
            try:
                await conn.execute(text(statement))
            except Exception:
                pass


async def close_db():
    """Close database connection."""
    await engine.dispose()
