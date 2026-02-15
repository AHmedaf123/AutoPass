"""
Clean FastAPI Main Application
Production-ready with clean endpoints
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from loguru import logger

from core.config import settings
from core.database import init_db, close_db

# Import clean routers
from presentation.api.v1.endpoints.auth import router as auth_router
from presentation.api.v1.endpoints.preferences_clean import router as preferences_router
from presentation.api.v1.endpoints.resume import router as resume_router
from presentation.api.v1.endpoints.jobs_clean import router as jobs_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting AI Job Auto-Applier API...")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down API...")
    await close_db()


# Create FastAPI app
app = FastAPI(
    title="AI Job Auto-Applier API",
    description="Production-ready job auto-application system",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(preferences_router, prefix="/api/v1", tags=["Preferences"])
app.include_router(resume_router, prefix="/api/v1", tags=["Resume"])
app.include_router(jobs_router, prefix="/api/v1", tags=["Jobs & Applications"])

# Health check
@app.get("/health")
@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "ai-job-auto-applier",
        "version": "2.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI Job Auto-Applier API",
        "version": "2.0.0",
        "docs": "/api/docs",
        "health": "/api/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main_clean:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
