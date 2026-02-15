"""
FastAPI Main Application
Entry point with all routers and middleware
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from core.config import settings
from core.logging_config import logger
from presentation.api.v1.endpoints import (
    preferences_router,
    jobs_router,
    auth_router
)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# Create FastAPI app
app = FastAPI(
    title="AI Job Auto-Applier API",
    description="Production-ready job application automation with BLS-aligned AI matching",
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Please try again later."}
))
app.add_middleware(SlowAPIMiddleware)

# Include API routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(preferences_router, prefix="/api/v1", tags=["preferences"])
app.include_router(jobs_router, prefix="/api/v1", tags=["jobs"])

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "3.0.0"}

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting AI Job Auto-Applier API v3.0.0")
    logger.info("BLS subfield integration: 107 occupational titles across 16 industries")
    
    # Initialize Redis cache
    try:
        from infrastructure.cache.redis_cache_service import cache_service
        await cache_service.connect()
        logger.info("Redis cache connected")
    except Exception as e:
        logger.warning(f"Redis cache connection failed: {e} - Running without cache")
    
    # Start background task worker
    try:
        from application.services.task_worker import start_worker
        import asyncio
        
        # Start worker in background
        poll_interval = getattr(settings, 'TASK_WORKER_POLL_INTERVAL', 5)
        max_concurrent = getattr(settings, 'TASK_WORKER_MAX_CONCURRENT', 3)
        
        asyncio.create_task(start_worker(poll_interval=poll_interval, max_concurrent_tasks=max_concurrent))
        logger.info(f"✅ Background task worker started (poll_interval={poll_interval}s, max_concurrent={max_concurrent})")
    except Exception as e:
        logger.error(f"❌ Failed to start background task worker: {e}")
        # Don't fail startup if worker fails to start
        logger.warning("Application will continue without background task worker")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down AI Job Auto-Applier API")
    
    # Stop background task worker
    try:
        from application.services.task_worker import stop_worker
        await stop_worker()
        logger.info("✅ Background task worker stopped")
    except Exception as e:
        logger.warning(f"Error stopping task worker: {e}")
    
    # Disconnect Redis
    try:
        from infrastructure.cache.redis_cache_service import cache_service
        await cache_service.disconnect()
    except Exception as e:
        logger.warning(f"Error disconnecting Redis: {e}")
