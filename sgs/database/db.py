"""
Database connection and initialization for SGS Trader.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sgs.config import Config
from sgs.database.models import Base
from sgs.utils.logging import get_logger

logger = get_logger("database")

# Global engine and session factory
_engine = None
_SessionFactory = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    
    if _engine is None:
        db_url = f"sqlite:///{Config.DB_FULL_PATH}"
        _engine = create_engine(
            db_url,
            echo=False,  # Set to True for SQL debugging
            connect_args={"check_same_thread": False}  # SQLite specific
        )
        logger.info(f"Database engine created: {Config.DB_FULL_PATH}")
    
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _SessionFactory
    
    if _SessionFactory is None:
        engine = get_engine()
        _SessionFactory = sessionmaker(bind=engine)
    
    return _SessionFactory


def get_session() -> Session:
    """
    Get a new database session.
    
    Usage:
        session = get_session()
        try:
            # Do database operations
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()
    
    Or use as context manager:
        with get_session() as session:
            # Do database operations
            session.commit()
    """
    SessionFactory = get_session_factory()
    return SessionFactory()


def init_db():
    """
    Initialize the database by creating all tables.
    This is idempotent - safe to call multiple times.
    """
    engine = get_engine()
    
    # Create all tables defined in models
    Base.metadata.create_all(engine)
    
    logger.info("Database initialized - all tables created")
    
    # Log table names
    table_names = Base.metadata.tables.keys()
    logger.info(f"Tables: {', '.join(table_names)}")


def reset_db():
    """
    Drop all tables and recreate them.
    WARNING: This will delete all data!
    """
    engine = get_engine()
    
    logger.warning("Dropping all tables - ALL DATA WILL BE LOST!")
    Base.metadata.drop_all(engine)
    
    logger.info("Recreating all tables")
    Base.metadata.create_all(engine)
    
    logger.info("Database reset complete")
