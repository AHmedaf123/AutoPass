"""Main FastAPI Application

Production-ready application implementing the FastAPI ASGI app used in
this project. This module wires middleware, global exception handlers,
and includes API routers from `presentation`.

Run locally for development with:

    uvicorn main:socket_app --reload

Keep application logic in `presentation`, `core`, and
`infrastructure` to preserve a clean architecture.
"""
import sys
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from core.config import settings
from core.database import init_db, close_db
from core.logging_config import configure_logging
from core.exceptions import (
    DomainException,
    AuthenticationException,
    AuthorizationException,
    ValidationException,
    ResourceNotFoundException,
    RateLimitException
)
from presentation.api.v1.endpoints.auth import router as auth_router
from presentation.api.v1.endpoints.jobs_clean import router as jobs_ws_router
from presentation.api.v1.endpoints.preferences_clean import router as preferences_router
from presentation.api.v1.endpoints.resume import router as resume_router
from presentation.api.v1.endpoints.jobs_clean import router as jobs_router
from presentation.routes.admin.metrics import router as metrics_router


# Socket.IO server for real-time updates
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins=settings.CORS_ORIGINS,
    logger=settings.DEBUG,
    engineio_logger=settings.DEBUG
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info(f"🚀 Starting {settings.APP_NAME} ({settings.ENVIRONMENT})...")
    
    # Initialize database
    await init_db()
    logger.info("✅ Database initialized")
    
    yield
    
    # Shutdown
    logger.info("👋 Shutting down gracefully...")
    await close_db()
    logger.info("✅ Database connections closed")


# Initialize FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    description="Production-ready AI Job Auto-Applier with Clean Architecture",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None
)


# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global Exception Handler
@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle domain-level exceptions"""
    logger.warning(f"Domain exception: {str(exc)}")
    
    if isinstance(exc, AuthenticationException):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(exc, AuthorizationException):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ValidationException):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    elif isinstance(exc, ResourceNotFoundException):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(exc, RateLimitException):
        status_code = status.HTTP_429_TOO_MANY_REQUESTS
    else:
        status_code = status.HTTP_400_BAD_REQUEST
    
    return JSONResponse(
        status_code=status_code,
        content={"detail": str(exc)}
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


# Include API routes
app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

# WebSocket endpoint for job scraping
app.include_router(
    jobs_ws_router,
    prefix="/api/v1/jobs",
    tags=["Jobs WebSocket"]
)

# Preferences endpoint
app.include_router(
    preferences_router,
    prefix="/api/v1",
    tags=["Preferences"]
)

# Resume endpoint
app.include_router(
    resume_router,
    prefix="/api/v1",
    tags=["Resume"]
)

# Jobs endpoint
app.include_router(
    jobs_router,
    prefix="/api/v1",
    tags=["Jobs"]
)

# Admin metrics endpoint
app.include_router(
    metrics_router,
    tags=["Admin Metrics"]
)


# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    logger.info(f"🔌 Client connected: {sid}")


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    logger.info(f"🔌 Client disconnected: {sid}")


@sio.event
async def authenticate(sid, data):
    """Authenticate user and join their room"""
    user_id = data.get('user_id')
    if user_id:
        sio.enter_room(sid, str(user_id))
        await sio.emit('authenticated', {'status': 'success'}, room=sid)
        logger.info(f"✅ User {user_id} authenticated in room")


# Wrap FastAPI with Socket.IO
socket_app = socketio.ASGIApp(
    sio,
    app,
    socketio_path='/socket.io'
)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:socket_app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
