import json
import asyncio
from datetime import datetime
from typing import AsyncGenerator, Optional
import redis.asyncio as redis

from app.config.settings import get_settings
from app.config.logging import get_logger, LogContext
from app.models.news import NewsStreamUpdate

logger = get_logger(__name__)
settings = get_settings()


class RedisStreamService:
    """Service for managing Redis pub/sub streams for real-time updates."""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.stream_key = settings.redis_stream_key
        
    async def _get_redis_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if not self.redis_client:
            self.redis_client = redis.from_url(settings.redis_url)
        return self.redis_client
    
    async def publish_update(
        self, 
        job_id: str, 
        status: str, 
        message: str, 
        data: Optional[dict] = None
    ):
        """
        Publish a status update to Redis stream.
        
        Args:
            job_id: Unique job identifier
            status: Current status
            message: Human-readable message
            data: Optional additional data
        """
        with LogContext(job_id=job_id, status=status):
            try:
                client = await self._get_redis_client()
                
                update = NewsStreamUpdate(
                    job_id=job_id,
                    status=status,
                    message=message,
                    timestamp=datetime.utcnow(),
                    data=data
                )
                
                # Publish to job-specific channel
                channel = f"news:{job_id}"
                await client.publish(channel, update.json())
                
                # Also add to stream for persistence
                stream_data = {
                    "job_id": job_id,
                    "status": status,
                    "message": message,
                    "timestamp": update.timestamp.isoformat(),
                    "data": json.dumps(data) if data else ""
                }
                
                await client.xadd(f"{self.stream_key}:{job_id}", stream_data)
                
                logger.debug("Published update", message=message)
                
            except Exception as e:
                logger.error("Failed to publish update", error=str(e))
                # Don't raise - we don't want to break the main workflow for streaming issues
    
    async def subscribe_to_updates(self, job_id: str) -> AsyncGenerator[NewsStreamUpdate, None]:
        """
        Subscribe to real-time updates for a specific job.
        
        Args:
            job_id: Unique job identifier
            
        Yields:
            NewsStreamUpdate objects
        """
        with LogContext(job_id=job_id, operation="subscribe_to_updates"):
            logger.info("Starting subscription to job updates")
            
            client = await self._get_redis_client()
            pubsub = client.pubsub()
            
            try:
                # Subscribe to job-specific channel
                channel = f"news:{job_id}"
                await pubsub.subscribe(channel)
                
                # First, send any existing updates from the stream
                async for update in self._get_existing_updates(job_id):
                    yield update
                
                # Then listen for new updates
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            update_data = json.loads(message["data"])
                            update = NewsStreamUpdate(**update_data)
                            
                            logger.debug("Received update", status=update.status)
                            yield update
                            
                            # Stop if job is finished
                            if update.status in ["completed", "failed"]:
                                logger.info("Job finished, stopping subscription")
                                break
                                
                        except Exception as e:
                            logger.error("Failed to parse update message", error=str(e))
                            continue
                
            except Exception as e:
                logger.error("Subscription error", error=str(e))
                raise
            finally:
                await pubsub.unsubscribe()
                await pubsub.aclose()
    
    async def _get_existing_updates(self, job_id: str) -> AsyncGenerator[NewsStreamUpdate, None]:
        """
        Get existing updates from the Redis stream.
        
        Args:
            job_id: Unique job identifier
            
        Yields:
            NewsStreamUpdate objects from existing stream
        """
        try:
            client = await self._get_redis_client()
            stream_key = f"{self.stream_key}:{job_id}"
            
            # Check if stream exists
            exists = await client.exists(stream_key)
            if not exists:
                logger.debug("No existing stream found", stream_key=stream_key)
                return
            
            # Read all messages from the stream
            messages = await client.xrange(stream_key)
            
            for message_id, fields in messages:
                try:
                    # Parse the stream data
                    data_json = fields.get(b"data", b"").decode()
                    data = json.loads(data_json) if data_json else None
                    
                    update = NewsStreamUpdate(
                        job_id=fields[b"job_id"].decode(),
                        status=fields[b"status"].decode(),
                        message=fields[b"message"].decode(),
                        timestamp=datetime.fromisoformat(fields[b"timestamp"].decode()),
                        data=data
                    )
                    
                    yield update
                    
                except Exception as e:
                    logger.error("Failed to parse stream message", error=str(e))
                    continue
                    
        except Exception as e:
            logger.error("Failed to read existing updates", error=str(e))
    
    async def get_job_updates(self, job_id: str) -> list[NewsStreamUpdate]:
        """
        Get all updates for a job from Redis stream.
        
        Args:
            job_id: Unique job identifier
            
        Returns:
            List of NewsStreamUpdate objects
        """
        updates = []
        async for update in self._get_existing_updates(job_id):
            updates.append(update)
        return updates
    
    async def cleanup_job_stream(self, job_id: str, max_age_hours: int = 24):
        """
        Cleanup old job streams to save memory.
        
        Args:
            job_id: Unique job identifier
            max_age_hours: Maximum age in hours to keep streams
        """
        try:
            client = await self._get_redis_client()
            stream_key = f"{self.stream_key}:{job_id}"
            
            # Calculate cutoff timestamp
            cutoff_time = datetime.utcnow().timestamp() - (max_age_hours * 3600)
            cutoff_ms = int(cutoff_time * 1000)
            
            # Delete old entries
            await client.xtrim(stream_key, minid=f"{cutoff_ms}-0", approximate=True)
            
            logger.debug("Cleaned up job stream", job_id=job_id, max_age_hours=max_age_hours)
            
        except Exception as e:
            logger.error("Failed to cleanup job stream", job_id=job_id, error=str(e))
    
    async def close(self):
        """Close Redis connections."""
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
            logger.info("Redis client closed")


# Global service instance
redis_stream_service = RedisStreamService()