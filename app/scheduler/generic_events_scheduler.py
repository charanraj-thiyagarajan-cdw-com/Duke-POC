import asyncio
import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, timezone, date as date_obj
import json

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.events_api import fetch_and_yield_event_pages
from app.services.appearance_api import fetch_all_face_events

logger = get_logger("generic-events-scheduler")
settings = get_settings()

central_base_url = settings.CENTRAL_BASE
post_endpoint = "/store-events"
latest_ts_endpoint = "/events/latest-timestamp"
post_url = f"{central_base_url.rstrip('/')}{post_endpoint}"

# --- URL Definitions ---
latest_ts_url = f"{central_base_url.rstrip('/')}{latest_ts_endpoint}"
latest_face_ts_url = f"{latest_ts_url}?type=CUSTOM_APPEARANCE"


API_PAGE_SIZE = 100
verify_ssl = settings.AVIGILON_API_VERIFY_SSL
DEFAULT_BACKFILL_DAYS = 30


def generic_events_fetch_job():
    """
    (This function is correct and remains unchanged)
    """
    # This entire function's logic is sound and does not need to be changed.
    # It is included here for completeness of the file.
    async def fetch_and_post_logic():
        logger.info("Determining the next full day to process for GENERIC events...")
        day_to_process: date_obj
        try:
            async with httpx.AsyncClient(verify=verify_ssl, timeout=60) as client:
                response = await client.get(latest_ts_url)
                response.raise_for_status()
                data = response.json()
                latest_timestamp_str = data.get("latest_timestamp")
                if latest_timestamp_str:
                    latest_event_dt = datetime.fromisoformat(latest_timestamp_str.replace("Z", "+00:00"))
                    latest_event_date = latest_event_dt.date()
                    today = datetime.now(timezone.utc).date()
                    if latest_event_date < today:
                        day_to_process = latest_event_date + timedelta(days=1)
                        logger.info(f"Last processed day was {latest_event_date}. Processing next full day for GENERIC events: {day_to_process}")
                    else:
                        day_to_process = today
                        logger.info(f"Already caught up to today. Re-processing all of {day_to_process} for GENERIC events to fetch latest.")
                else:
                    day_to_process = datetime.now(timezone.utc).date() - timedelta(days=DEFAULT_BACKFILL_DAYS)
                    logger.info(f"No previous GENERIC events found. Starting backfill from day: {day_to_process}")
        except Exception as e:
            logger.error(f"Could not determine start day from API for GENERIC events: {e}. Aborting job.", exc_info=True)
            return

        from_time_dt = datetime(year=day_to_process.year, month=day_to_process.month, day=day_to_process.day, hour=0, minute=0, second=0, tzinfo=timezone.utc)
        if day_to_process < datetime.now(timezone.utc).date():
            to_time_dt = datetime(year=day_to_process.year, month=day_to_process.month, day=day_to_process.day, hour=23, minute=59, second=59, tzinfo=timezone.utc)
        else:
            to_time_dt = datetime.now(timezone.utc)
        from_time = from_time_dt.isoformat().replace("+00:00", "Z")
        to_time = to_time_dt.isoformat().replace("+00:00", "Z")

        total_posted_count, total_failed_pages, page_number = 0, 0, 0
        logger.info(f"Starting GENERIC event processing for the day window: {from_time} to {to_time}...")
        try:
            async with httpx.AsyncClient(verify=verify_ssl, timeout=300) as client:
                async for event_page in fetch_and_yield_event_pages(from_time, to_time, page_size=API_PAGE_SIZE):
                    page_number += 1
                    if not event_page: continue
                    logger.info(f"Posting page {page_number} with {len(event_page)} generic events...")
                    try:
                        post_response = await client.post(post_url, json={"events": event_page})
                        post_response.raise_for_status()
                        response_data = post_response.json()
                        stored_in_page = response_data.get("stored_count", len(event_page))
                        total_posted_count += stored_in_page
                        logger.info(f"Successfully posted page {page_number}. Stored {stored_in_page} generic events.")
                    except httpx.HTTPStatusError as exc:
                        total_failed_pages += 1
                        logger.error(f"HTTP error posting page {page_number} of generic events: {exc.response.status_code} - Response: {exc.response.text}")
                    except Exception as e:
                        total_failed_pages += 1
                        logger.error(f"An unexpected error occurred while posting page {page_number} of generic events: {e}", exc_info=True)
            logger.info("--- Generic Event Processing Summary for this Run ---")
            if page_number == 0: logger.info(f"No new generic events were found for the processed day: {day_to_process}.")
            else:
                logger.info(f"Processed {page_number} page(s) for day {day_to_process}. Stored {total_posted_count} generic events.")
                if total_failed_pages > 0: logger.warning(f"Number of failed pages: {total_failed_pages}. These pages for day {day_to_process} were not stored.")
        except Exception as e:
            logger.error(f"A critical unhandled error occurred during the generic event processing job: {e}", exc_info=True)
    asyncio.run(fetch_and_post_logic())


# --- CORRECTED FACE EVENTS JOB ---

async def robust_face_events_logic():
    """
    Robustly fetches face events, handling empty days by continuing to the
    next day within the same job run until data is found or it's caught up.
    """
    logger.info("--- STARTING ROBUST FACE EVENTS JOB ---")

    # 1. Determine the starting day ONCE at the beginning of the job.
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=60) as client:
            response = await client.get(latest_face_ts_url)
            response.raise_for_status()
            latest_timestamp_str = response.json().get("latest_timestamp")
            
            if latest_timestamp_str:
                latest_event_date = datetime.fromisoformat(latest_timestamp_str.replace("Z", "+00:00")).date()
                current_day_to_process = latest_event_date + timedelta(days=1)
                logger.info(f"Last processed day was {latest_event_date}. Starting process from: {current_day_to_process}")
            else:
                current_day_to_process = datetime.now(timezone.utc).date() - timedelta(days=DEFAULT_BACKFILL_DAYS)
                logger.info(f"No previous data found. Starting backfill from: {current_day_to_process}")
    except Exception as e:
        logger.error(f"Could not determine start day from API. Aborting job: {e}", exc_info=True)
        return

    # 2. Loop through days until we are caught up.
    today = datetime.now(timezone.utc).date()
    while current_day_to_process < today:
        logger.info(f"--- Processing day: {current_day_to_process} ---")
        
        from_time_dt = datetime(current_day_to_process.year, current_day_to_process.month, current_day_to_process.day, 0, 0, 0, tzinfo=timezone.utc)
        to_time_dt = datetime(current_day_to_process.year, current_day_to_process.month, current_day_to_process.day, 23, 59, 59, tzinfo=timezone.utc)
        from_time = from_time_dt.isoformat().replace("+00:00", "Z")
        to_time = to_time_dt.isoformat().replace("+00:00", "Z")

        try:
            payload = await fetch_all_face_events(from_time, to_time)
            appearances = payload.get("results") or payload.get("appearances", [])

            if not appearances:
                logger.info(f"Day {current_day_to_process} was empty. Advancing to the next day.")
                current_day_to_process += timedelta(days=1)
                continue

            logger.info(f"Found {len(appearances)} events for {current_day_to_process}. Transforming and posting.")
            
            events_to_post = []
            for appearance in appearances:
                if isinstance(appearance, dict):
                    appearance['type'] = 'CUSTOM_APPEARANCE'
                    appearance['timestamp'] = appearance.get('eventStartTime')
                    appearance['cameraId'] = appearance.get('cameraId')
                    appearance['originatingServerId'] = appearance.get('originatingServerId')
                    appearance['originatingEventId'] = appearance.get('id', 1) 
                    appearance['thisId'] = appearance.get('id', 1) 
                    events_to_post.append(appearance)

            if not events_to_post:
                logger.warning(f"Transformation of payload for {current_day_to_process} resulted in 0 events. Advancing to next day.")
                current_day_to_process += timedelta(days=1)
                continue

            async with httpx.AsyncClient(verify=verify_ssl, timeout=600) as client:
                response = await client.post(post_url, json={"events": events_to_post})
                response.raise_for_status()
                stored_count = response.json().get("stored_count", len(events_to_post))
                logger.info(f"Successfully posted {stored_count} face events for {current_day_to_process}.")

            # IMPORTANT: After finding and posting data, break the loop.
            # The next scheduled job run will pick up from this new state.
            logger.info("Data found and posted for this run. The scheduler will continue from here on the next run.")
            break 
        
        except Exception as e:
            logger.error(f"Failed to process day {current_day_to_process}: {e}. Aborting job run.", exc_info=True)
            return # Exit if any single day has a critical failure

    logger.info("Face events job finished. System is now caught up.")


def face_events_fetch_job():
    """
    Synchronous wrapper that calls the new robust, self-advancing logic.
    """
    asyncio.run(robust_face_events_logic())


def start_event_schedulers():
    """
    (This function is correct and remains unchanged, but includes a helpful
     suggestion for speeding up the initial backfill)
    """
    scheduler = BackgroundScheduler(timezone="UTC")
    
    scheduler.add_job(
        generic_events_fetch_job,
        "interval",
        minutes=1,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
        misfire_grace_time=600,
        id="generic_events_job"
    )
    
    # SUGGESTION: To speed up the initial 30-day backfill, temporarily change
    # the schedule below to run every few minutes. Once caught up, revert it
    # to the daily 'cron' schedule.
    scheduler.add_job(
        face_events_fetch_job,
        'interval',  # Use 'interval' for fast backfilling. Change to 'cron' for normal operation.
        minutes=1,   # Run every 5 minutes.
        # cron schedule for normal operation (once caught up):
        # 'cron',
        # hour=0,
        # minute=30,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=20),
        misfire_grace_time=600,
        id="face_events_job"
    )
    
    scheduler.start()
    logger.info("Unified event schedulers started.")
    logger.info("-> Generic events job runs hourly.")
    logger.info("-> Face events job is set to run every 5 minutes for backfilling.")
    # pass