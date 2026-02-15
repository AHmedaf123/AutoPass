import json
from typing import Optional, Any
import redis.asyncio as redis
from redis.asyncio import Redis

from core.config import settings
from core.logging_config import logger


class RedisCacheService:
    """Redis cache service for preferences, jobs, and embeddings"""
    
    def __init__(self):
        """Initialize Redis connection"""
        self._redis: Optional[Redis] = None
    
    async def connect(self):
        """Connect to Redis"""
        try:
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379/0')
            # Use dictionary unpacking to avoid type errors if encoding/decode_responses logic differs
            self._redis = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            logger.info(f"Connected to Redis: {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            # Don't raise - allow app to run without cache
            self._redis = None
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self._redis:
            await self._redis.close()
            logger.info("Disconnected from Redis")
    
    async def get(self, key: str) -> Optional[str]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if not self._redis:
            return None
        
        try:
            return await self._redis.get(key)
        except Exception as e:
            logger.error(f"Redis GET error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: str, ttl: int = 3600):
        """
        Set value in cache with TTL
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default 1 hour)
        """
        if not self._redis:
            return
        
        try:
            await self._redis.setex(key, ttl, value)
            logger.debug(f"Cached key {key} with TTL {ttl}s")
        except Exception as e:
            logger.error(f"Redis SET error for key {key}: {e}")
    
    async def delete(self, key: str):
        """
        Delete key from cache
        
        Args:
            key: Cache key
        """
        if not self._redis:
            return
        
        try:
            await self._redis.delete(key)
            logger.debug(f"Deleted key {key}")
        except Exception as e:
            logger.error(f"Redis DELETE error for key {key}: {e}")
    
    async def get_json(self, key: str) -> Optional[Any]:
        """
        Get JSON value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Deserialized JSON or None
        """
        value = await self.get(key)
        if not value:
            return None
        
        try:
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for key {key}: {e}")
            return None
    
    async def set_json(self, key: str, value: Any, ttl: int = 3600):
        """
        Set JSON value in cache
        
        Args:
            key: Cache key
            value: Value to serialize and cache
            ttl: Time to live in seconds
        """
        try:
            json_value = json.dumps(value)
            await self.set(key, json_value, ttl)
        except (TypeError, ValueError) as e:
            logger.error(f"JSON encode error for key {key}: {e}")
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self._redis:
            return False
        
        try:
            return await self._redis.exists(key) > 0
        except Exception as e:
            logger.error(f"Redis EXISTS error for key {key}: {e}")
            return False


# Global cache instance
cache_service = RedisCacheService()
