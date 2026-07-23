"""
Database configuration and setup for DataHire platform.
"""

import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

logger = logging.getLogger(__name__)

# Create engine based on database URL
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Enable SQL logging in debug mode
    pool_pre_ping=True,
    pool_recycle=1800,
    # SQLite specific settings
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

# Create session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    """Dependency to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables."""
    # Import all models to ensure they are registered
    from app.models import Base
    
    # Register event listeners for automatic embedding generation
    from app.db.embedding_listener import register_embedding_listeners
    register_embedding_listeners()
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
