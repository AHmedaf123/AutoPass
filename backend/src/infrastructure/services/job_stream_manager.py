"""
Job Stream Manager
Manages real-time job discovery streaming via Server-Sent Events (SSE)
Handles broadcasting newly discovered jobs to connected clients
"""
import asyncio
from typing import Dict, Set, Callable, Optional, Union
from dataclasses import dataclass
from loguru import logger


@dataclass
class JobDiscoveryEvent:
    """A newly discovered job event to be streamed to clients"""
    job_id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    work_type: Optional[str] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    match_score: Optional[float] = None
    
    def to_sse_data(self) -> str:
        """Convert to SSE data format"""
        import json
        data = {
            "job_id": self.job_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "description": self.description,
            "url": self.url,
            "work_type": self.work_type,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "match_score": self.match_score,
        }
        return json.dumps(data)


@dataclass
class StreamStatusEvent:
    """Status or notification event (errors, warnings, no jobs found, etc.)"""
    type: str  # 'error', 'warning', 'no_jobs', 'info'
    message: str
    data: Optional[dict] = None
    
    def to_sse_data(self) -> str:
        """Convert to SSE data format"""
        import json
        event_data = {
            "type": self.type,
            "message": self.message,
        }
        if self.data:
            event_data["data"] = self.data
        return json.dumps(event_data)


class JobStreamManager:
    """
    Manages real-time job discovery streaming.
    Maintains active SSE connections and broadcasts new job events.
    
    Usage:
        manager = JobStreamManager()
        
        # Client connects
        async for event in manager.subscribe(session_id):
            yield event
        
        # Server publishes new job
        await manager.publish_job(session_id, job_event)
        
        # End stream
        await manager.complete_stream(session_id)
    """
    
    def __init__(self):
        # Maps session_id -> queue of events waiting to be sent
        self._queues: Dict[str, asyncio.Queue] = {}
        # Maps session_id -> stream completion flag
        self._completed: Dict[str, bool] = {}
        # Maps session_id -> active flag (client still connected)
        self._active: Dict[str, bool] = {}
    
    async def subscribe(self, session_id: str):
        """
        Subscribe to job discovery events for a session.
        Yields SSE-formatted data for each new job discovered.
        Closes when complete_stream() is called.
        
        Usage in FastAPI endpoint:
            async def stream_jobs(session_id: str):
                async for event_data in manager.subscribe(session_id):
                    yield f"data: {event_data}\n\n"
        """
        # Initialize queue for this session
        self._queues[session_id] = asyncio.Queue()
        self._completed[session_id] = False
        self._active[session_id] = True
        
        logger.info(f"📡 Client subscribed to job stream: {session_id}")
        
        try:
            while True:
                # Check if stream is completed
                if self._completed[session_id]:
                    logger.info(f"✅ Job stream completed for session: {session_id}")
                    # Send completion marker
                    yield f"data: {{'status': 'completed'}}\n\n"
                    break
                
                # Wait for next event with timeout to check completion status
                try:
                    event: Union[JobDiscoveryEvent, StreamStatusEvent] = await asyncio.wait_for(
                        self._queues[session_id].get(),
                        timeout=30.0  # 30 second timeout
                    )
                    
                    # Yield the event data in SSE format
                    event_data = event.to_sse_data()
                    yield f"data: {event_data}\n\n"
                    
                except asyncio.TimeoutError:
                    # Check if still active
                    if not self._active[session_id]:
                        logger.info(f"⏱️  Job stream timeout for inactive session: {session_id}")
                        break
                    # Otherwise keep waiting
                    continue
        
        finally:
            self._cleanup(session_id)
    
    async def publish_job(self, session_id: str, job: JobDiscoveryEvent):
        """
        Publish a newly discovered job to the stream.
        Non-blocking - queues the event for the client to receive.
        """
        if session_id not in self._queues:
            logger.warning(f"⚠️  Session {session_id} not subscribed, creating queue")
            self._queues[session_id] = asyncio.Queue()
            self._completed[session_id] = False
            self._active[session_id] = True
        
        if self._active[session_id]:
            await self._queues[session_id].put(job)
            logger.debug(f"📤 Published job to session {session_id}: {job.title}")
    
    async def send_event(self, session_id: str, event: StreamStatusEvent):
        """
        Send a status/notification event to the stream.
        Used for errors, warnings, no jobs found, etc.
        Non-blocking - queues the event for the client to receive.
        """
        if session_id not in self._queues:
            logger.warning(f"⚠️  Session {session_id} not subscribed, creating queue")
            self._queues[session_id] = asyncio.Queue()
            self._completed[session_id] = False
            self._active[session_id] = True
        
        if self._active[session_id]:
            await self._queues[session_id].put(event)
            logger.debug(f"📤 Sent {event.type} event to session {session_id}: {event.message}")
    
    async def complete_stream(self, session_id: str):
        """
        Signal that job discovery is complete for this session.
        Client will receive completion marker and connection closes.
        """
        if session_id in self._completed:
            self._completed[session_id] = True
            logger.info(f"🏁 Marked job stream as complete for session: {session_id}")
    
    def mark_inactive(self, session_id: str):
        """Mark session as inactive (client disconnected)"""
        if session_id in self._active:
            self._active[session_id] = False
            logger.info(f"💤 Marked session as inactive: {session_id}")
    
    def _cleanup(self, session_id: str):
        """Clean up resources for a session"""
        if session_id in self._queues:
            del self._queues[session_id]
        if session_id in self._completed:
            del self._completed[session_id]
        if session_id in self._active:
            del self._active[session_id]
        logger.info(f"🧹 Cleaned up job stream session: {session_id}")


# Global instance
_stream_manager: Optional[JobStreamManager] = None


def get_stream_manager() -> JobStreamManager:
    """Get or create global stream manager"""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = JobStreamManager()
    return _stream_manager
