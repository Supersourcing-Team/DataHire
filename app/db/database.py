"""
Database configuration and setup for DataHire platform.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Create engine based on database URL
engine = create_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,  # Enable SQL logging in debug mode
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
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully")
