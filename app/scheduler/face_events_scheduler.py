import asyncio
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
from app.core.logging import get_logger
from app.core.config import get_settings
from app.services.appearance_api import fetch_all_face_events
import httpx

logger = get_logger("face-events-scheduler")
settings = get_settings()
central_base = settings.CENTRAL_BASE
verify_ssl = settings.AVIGILON_API_VERIFY_SSL
post_url = f"{central_base}/store-appearances"

def all_face_events_fetch():
    async def fetch_logic():
        now = datetime.now()
        prev_day = now - timedelta(days=1)
        from_time = prev_day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        to_time = prev_day.replace(hour=23, minute=59, second=59, microsecond=999000).isoformat() + 'Z'
        try:
            logger.info(f"Fetching face events from {from_time} to {to_time} at {now}...")
            payload = await fetch_all_face_events(from_time, to_time)
            logger.info(f"Fetched {payload['total_length']} face events for {from_time} to {to_time}")
            async with httpx.AsyncClient(verify=verify_ssl, timeout=600) as client:
                response = await client.post(post_url, json=payload)
                logger.info(f"Posted results central analytics app: {response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching face events: {e}")
    asyncio.run(fetch_logic())

def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(all_face_events_fetch, 'cron', hour=0, minute=30, misfire_grace_time=60)
    scheduler.start()
    logger.info("Face events scheduler started (runs daily at 12:30am)")
    # pass
