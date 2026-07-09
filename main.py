from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging

from app.core.config import settings
from app.core.logging import setup_logging
from app.core.exceptions import BaseCustomException
from app.api.v1.api import api_router

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting DataHire application...")
    
    # Register automatic embedding generation listeners
    from app.db.embedding_listener import register_embedding_listeners
    register_embedding_listeners()
    logger.info("Registered SQLAlchemy embedding listeners")

    # Start background Redis notification listener
    import asyncio
    from app.core.redis_listener import redis_notification_listener
    listener_task = asyncio.create_task(redis_notification_listener())
    logger.info("Started background Redis Pub/Sub notification listener task")
    
    yield
    
    # Clean up background task on shutdown
    logger.info("Shutting down background Redis Pub/Sub listener task...")
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down DataHire application...")

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler
@app.exception_handler(BaseCustomException)
async def custom_exception_handler(request: Request, exc: BaseCustomException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "type": exc.__class__.__name__}
    )

# Include API router
app.include_router(api_router, prefix="/api/v1")

@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "DataHire API",
        "version": settings.APP_VERSION,
        "docs": "/api/v1/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": settings.APP_VERSION}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
