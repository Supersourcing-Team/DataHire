import json
import asyncio
import logging
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.websocket_manager import manager

logger = logging.getLogger(__name__)

async def redis_notification_listener():
    """
    Background worker that listens on Redis Pub/Sub channel 'datahire_notifications'
    and dispatches messages to the connected WebSockets on this instance.
    """
    redis_url = settings.REDIS_URL or "redis://localhost:6379"
    logger.info(f"Starting Redis Pub/Sub listener connecting to {redis_url}...")

    while True:
        try:
            # Connect using redis-py async client with context managers to prevent connection leaks
            async with aioredis.from_url(redis_url) as client:
                async with client.pubsub() as pubsub:
                    await pubsub.subscribe("datahire_notifications")
                    logger.info("Successfully subscribed to Redis channel 'datahire_notifications'")

                    while True:
                        try:
                            # Read message with a timeout so it doesn't block indefinitely (allowing clean exit if needed)
                            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                            if message:
                                data_str = message.get("data")
                                if data_str:
                                    if isinstance(data_str, bytes):
                                        data_str = data_str.decode("utf-8")
                                    
                                    logger.info(f"Received pub/sub notification message: {data_str}")
                                    try:
                                        payload = json.loads(data_str)
                                        user_id = payload.get("user_id")
                                        if user_id:
                                            # Send message to WebSocket connections on this node
                                            await manager.send_personal_message(payload, user_id)
                                    except json.JSONDecodeError as decode_err:
                                        logger.error(f"Failed to decode Redis message: {str(decode_err)}")
                                    except Exception as dispatch_err:
                                        logger.error(f"Failed to dispatch WebSocket message: {str(dispatch_err)}")
                                        
                        except aioredis.ConnectionError:
                            logger.warning("Redis Pub/Sub connection lost inside the loop.")
                            break
                        except Exception as loop_err:
                            logger.error(f"Error in Redis Pub/Sub loop: {str(loop_err)}")
                            await asyncio.sleep(1.0)

        except aioredis.ConnectionError:
            logger.warning("Redis connection failed. Reconnecting in 5 seconds...")
            await asyncio.sleep(5.0)
        except Exception as e:
            logger.error(f"Unexpected error in Redis Pub/Sub listener: {str(e)}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5.0)
