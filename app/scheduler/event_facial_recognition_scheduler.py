import asyncio
import httpx
import base64
from typing import List, Dict, Any
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timezone

from app.core.logging import get_logger
from app.core.config import get_settings
# Assuming this service returns an object with FaceId and a model_dump method
from app.services.aws_services import process_all_faces_in_image

logger = get_logger("event-facial-recognition-scheduler")
settings = get_settings()

central_base_url = settings.CENTRAL_BASE
verify_ssl = settings.AVIGILON_API_VERIFY_SSL
# Using relative paths is fine if base_url is set on the client
fetch_url = f"{central_base_url.rstrip('/')}/events/for-recognition"
update_url = f"{central_base_url.rstrip('/')}/events/with-recognition"
FETCH_LIMIT = 100  # How many events to process per run


async def process_events_for_facial_recognition_job():
    """The main job function that orchestrates fetching, processing, and updating."""
    logger.info("Starting facial recognition job for events...")
    total_processed_count = 0

    try:
        async with httpx.AsyncClient(base_url=central_base_url, verify=verify_ssl, timeout=120) as client:
            while True:
                updates_to_send: List[Dict[str, Any]] = []

                logger.info(f"Fetching next batch of up to {FETCH_LIMIT} events...")
                fetch_response = await client.get(fetch_url, params={"limit": FETCH_LIMIT})
                fetch_response.raise_for_status()
                events_to_process = fetch_response.json().get("events", [])

                if not events_to_process:
                    logger.info("No new events found. The job has processed all available records.")
                    break

                batch_size = len(events_to_process)
                total_processed_count += batch_size
                logger.info(f"Found {batch_size} events in this batch. Processing...")

                for event in events_to_process:
                    event_id = event.get("_id")
                    image_b64 = event.get("imageBaseString")

                    if not event_id or not image_b64:
                        logger.warning(f"Skipping event due to missing '_id' or 'imageBaseString'.")
                        continue

                    try:
                        image_bytes = base64.b64decode(image_b64)
                        
                        # --- THIS IS THE MAIN LOGIC CHANGE ---
                        # 1. Call the new function which returns a list of results
                        list_of_face_results = process_all_faces_in_image(image_bytes)
                        
                        # 2. Build the final update payload using the new model structure
                        update_payload = {
                            "eventId": event_id,
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "detected_faces": list_of_face_results  # Assign the whole list here
                        }
                        
                        updates_to_send.append(update_payload)
                        logger.info(f"Prepared update for event {event_id} with {len(list_of_face_results)} detected face(s).")
                        # --- END OF LOGIC CHANGE ---

                    except Exception as e:
                        logger.error(f"Critical error processing image for event {event_id}: ", exc_info=True)
                        # Create a payload that still matches the model, but indicates a top-level error
                        error_payload = {
                             "eventId": event_id,
                             "processed_at": datetime.now(timezone.utc).isoformat(),
                             "detected_faces": [{
                                 "status": "error",
                                 "error_message": f"Scheduler-side error before AWS processing: {str(e)}"
                             }]
                        }
                        updates_to_send.append(error_payload)

                if updates_to_send:
                    logger.info(f"Sending {len(updates_to_send)} facial recognition updates to central for this batch.")
                    update_response = await client.post(update_url, json={"updates": updates_to_send})
                    if update_response.status_code >= 400:
                         logger.error(f"HTTP Error {update_response.status_code} posting updates. Response: {update_response.text}")
                    update_response.raise_for_status()
                    logger.info(f"Successfully posted updates for batch. Response: {update_response.json()}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during facial recognition job: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        logger.error(f"An unexpected error occurred in the facial recognition scheduler: ", exc_info=True)
    
    finally:
        logger.info(f"Facial recognition job finished. Total events processed in this run: {total_processed_count}.")


def run_async_facial_recognition_job():
    """
    This is the synchronous wrapper function. Its only job is to create an
    event loop and run our main async function until it's complete.
    """
    try:
        asyncio.run(process_events_for_facial_recognition_job())
    except Exception:
        logger.error("The async job runner for facial recognition crashed.", exc_info=True)


def start_event_facial_recognition_scheduler():
    # """Initializes and starts the background scheduler."""
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_async_facial_recognition_job,  # Point the scheduler to our new synchronous wrapper
        "interval",
        minutes=1, # Run every 5 minutes to keep up
        next_run_time=datetime.now(timezone.utc),
        misfire_grace_time=300, # 10 minutes
    )
    scheduler.start()
    logger.info("Event facial recognition scheduler started (runs every day).")
    pass
