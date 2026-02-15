"""Backend entrypoint: FastAPI app with Socket.IO integration.

This file defines the ASGI application used to run the API and provides
basic health and Socket.IO handlers. Run locally with:

    uvicorn main:socket_app --reload

Keep this file small — application logic lives under `src/` and `resume/`.
"""

import socketio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from core.database import engine, Base
from resume.router import router as resume_router


# Socket.IO server for real-time updates
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("🚀 Starting AI Job Auto-Applier API...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created")
    
    yield
    
    # Shutdown
    print("👋 Shutting down API...")


# Initialize FastAPI app
app = FastAPI(
    title="AI Job Auto-Applier API",
    description="Production-ready job auto-application system with AI matching",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware for React Native
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(resume_router, tags=["Resume"])

@app.get("/health")
async def health_check():
    """Health check endpoint for deployment monitoring"""
    return {
        "status": "healthy",
        "service": "ai-job-auto-applier",
        "version": "1.0.0"
    }


# Socket.IO event handlers
@sio.event
async def connect(sid, environ):
    """Handle client connection"""
    print(f"🔌 Client connected: {sid}")


@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    print(f"🔌 Client disconnected: {sid}")


@sio.event
async def authenticate(sid, data):
    """Authenticate user and join their room for targeted updates"""
    user_id = data.get('user_id')
    if user_id:
        sio.enter_room(sid, str(user_id))
        await sio.emit('authenticated', {'status': 'success'}, room=sid)
        print(f"✅ User {user_id} authenticated in room")


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
        reload=True
    )
