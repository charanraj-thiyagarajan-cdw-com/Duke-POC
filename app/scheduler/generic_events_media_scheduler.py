import asyncio
import httpx
import base64
from typing import List, Dict, Any, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.media_api import get_media_service

logger = get_logger("generic-events-media-scheduler")
settings = get_settings()

central_base_url = settings.CENTRAL_BASE
verify_ssl = settings.AVIGILON_API_VERIFY_SSL

# --- API Endpoints for the Central Application ---
# NOTE: These endpoints must be created in your central application.
# 1. GETs events that need their media field populated.
EVENTS_FOR_ENRICHMENT_URL = f"{central_base_url.rstrip('/')}/events-for-enrichment"
# 2. PATCHes/POSTs events with the new media data.
UPDATE_EVENTS_MEDIA_URL = f"{central_base_url.rstrip('/')}/events/media"

# --- Configuration ---
TARGET_EVENT_TYPE = "DEVICE_CLASSIFIED_OBJECT_MOTION_START"
BATCH_SIZE = 10  # How many events to fetch and process in a single batch.


async def _fetch_and_encode_media(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Fetches JPEG media for a single event and returns an update payload.
    JSON fetching is temporarily commented out.
    """
    event_id = event.get("_id")
    camera_id = event.get("cameraId")
    timestamp = event.get("timestamp")

    if not all([event_id, camera_id, timestamp]):
        logger.warning(f"Skipping event due to missing data needed for media fetch: {event}")
        return None

    update_payload = {"eventId": event_id}
    
    # --- JSON Fetching (Commented Out) ---
    # To re-enable, uncomment the task creation and add it to asyncio.gather below.
    # json_task = get_media_service(camera_id, timestamp, "json")
    
    # Fetch JPEG media
    jpeg_task = get_media_service(camera_id, timestamp, "jpeg")

    # return_exceptions=True prevents one failed request from stopping the others.
    # When re-enabling JSON, the gather call should be:
    # results = await asyncio.gather(json_task, jpeg_task, return_exceptions=True)
    # json_media_resp, jpeg_media_resp = results
    results = await asyncio.gather(jpeg_task, return_exceptions=True)
    jpeg_media_resp = results[0] # Get the first (and only) result from the list.

    # --- Process JSON media response (Commented Out) ---
    # if isinstance(json_media_resp, httpx.Response) and json_media_resp.status_code == 200:
    #     # Store the response body as raw text, as it may not be strict JSON.
    #     update_payload["json"] = json_media_resp.text
    # else:
    #     # Log either the failed response status or the exception that occurred.
    #     reason = json_media_resp if isinstance(json_media_resp, Exception) else getattr(json_media_resp, 'status_code', 'N/A')
    #     logger.warning(
    #         f"Failed to fetch JSON media for event {event_id}. Reason: {reason}"
    #     )

    # Process JPEG media response
    if isinstance(jpeg_media_resp, httpx.Response) and jpeg_media_resp.status_code == 200:
        update_payload["imageBaseString"] = base64.b64encode(jpeg_media_resp.content).decode("utf-8")
    else:
        # Log either the failed response status or the exception that occurred.
        reason = jpeg_media_resp if isinstance(jpeg_media_resp, Exception) else getattr(jpeg_media_resp, 'status_code', 'N/A')
        logger.warning(
            f"Failed to fetch JPEG media for event {event_id}. Reason: {reason}"
        )

    # Only return a payload if the image was successfully fetched
    if "imageBaseString" in update_payload:
        return update_payload

    logger.error(f"Failed to fetch any media for event {event_id}.")
    return None


async def enrich_events_job_logic():
    """The core async logic for the media enrichment job."""
    logger.info("Starting generic event media enrichment job...")
    total_enriched_count = 0

    try:
        # Use more granular timeouts: 10s to connect, 60s to read the response.
        # This helps fail faster if the service is unreachable.
        timeout_config = httpx.Timeout(10.0, read=60.0)
        async with httpx.AsyncClient(verify=verify_ssl, timeout=timeout_config) as client:
            while True:
                # 1. Fetch a batch of events that need enrichment from your central app
                logger.info(f"Fetching a batch of up to {BATCH_SIZE} events to enrich...")
                try:
                    params = {"type": TARGET_EVENT_TYPE, "limit": BATCH_SIZE}
                    resp = await client.get(EVENTS_FOR_ENRICHMENT_URL, params=params)
                    resp.raise_for_status()
                    events_to_process = resp.json().get("events", [])
                except httpx.RequestError as e:
                    logger.error(
                        f"Could not connect to central app at {EVENTS_FOR_ENRICHMENT_URL}. Please check network connectivity.",
                        exc_info=True)
                    break
                except httpx.HTTPStatusError as e:
                    logger.error(f"Failed to fetch events for enrichment: {e.response.status_code} - {e.response.text}")
                    break

                if not events_to_process:
                    logger.info("No more events to enrich. Job finished for this run.")
                    break

                logger.info(f"Found {len(events_to_process)} events. Fetching media concurrently...")

                # 2. Concurrently fetch media for the entire batch
                enrichment_tasks = [_fetch_and_encode_media(event) for event in events_to_process]
                update_payloads = await asyncio.gather(*enrichment_tasks)
                valid_updates = [p for p in update_payloads if p is not None]

                if not valid_updates:
                    logger.warning("No media could be fetched for the current batch.")
                    if len(events_to_process) < BATCH_SIZE: break
                    else: continue

                # 3. Post the batch of updates back to the central application
                # logger.info("Update payloads: %s", valid_updates)

                logger.info(f"Posting {len(valid_updates)} media updates back to the central app...")
                try:
                    update_resp = await client.post(UPDATE_EVENTS_MEDIA_URL, json={"updates": valid_updates})
                    update_resp.raise_for_status()
                    updated_count = update_resp.json().get("updated_count", len(valid_updates))
                    total_enriched_count += updated_count
                    logger.info(f"Successfully updated {updated_count} events with media.")
                except httpx.HTTPStatusError as e:
                    logger.error(f"Failed to post media updates: {e.response.status_code} - {e.response.text}")

                if len(events_to_process) < BATCH_SIZE:
                    logger.info("Processed the last available batch of events.")
                    break
    except Exception as e:
        logger.error(f"A critical unhandled error occurred during the enrichment job: {e}", exc_info=True)

    logger.info(f"--- Media Enrichment Summary ---")
    logger.info(f"Total events enriched in this run: {total_enriched_count}")


def generic_events_media_enrichment_job():
    """Synchronous wrapper for APScheduler."""
    asyncio.run(enrich_events_job_logic())
    # pass


def start_generic_events_media_scheduler():
    """Starts the background scheduler for the media enrichment job."""
    scheduler = BackgroundScheduler(timezone="UTC")
    # Runs daily at a specific time (e.g., 2:15 AM UTC).
    scheduler.add_job(
        generic_events_media_enrichment_job,
        "interval",
        hours=1, # Run every hour to catch up on "today's" data.
        next_run_time=datetime.now(timezone.utc),
        misfire_grace_time=600, # 10 minutes
    )
    scheduler.start()
    logger.info("Generic events media enrichment scheduler started (runs daily at 02:15 UTC).")
    # pass