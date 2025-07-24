import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from typing import Optional, List, Dict, Any
from app.services.avigilon_api import get_cameras_service, get_appearance_descriptions_service, get_sites_service
from app.services.media_api import get_media_service
import base64
import asyncio


settings = get_settings()
verify_ssl = settings.AVIGILON_API_VERIFY_SSL
AVIGILON_BASE = settings.AVIGILON_BASE
logger = get_logger("avigilon-appearance-service")


async def search_appearance_service(
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    appearances: Optional[dict] = None,
    camera_ids: Optional[list] = None,
    limit: Optional[int] = 100,
    scan_type: Optional[str] = "FULL",
    token: Optional[str] = None
):
    url = f"{AVIGILON_BASE}/appearance/search"
    if token:
        form_data = {
            "session": settings.SESSION_TOKEN,
            "queryType": "CONTINUE",
            "token": token
        }
    else:
        form_data = {
            "session": settings.SESSION_TOKEN,
            "queryType": "TIME_RANGE",
            "appearances": appearances,
            "from": from_time,
            "to": to_time,
            "cameraIds": camera_ids,
            "limit": limit,
            "scanType": scan_type
        }
    return await _make_appearance_search_request(url, form_data)

async def search_by_description_service(
    from_time: Optional[str] = None,
    to_time: Optional[str] = None,
    query_descriptors: Optional[list] = None,
    camera_ids: Optional[list] = None,
    limit: Optional[int] = 100,
    scan_type: Optional[str] = "FULL",
    token: Optional[str] = None
):
    url = f"{AVIGILON_BASE}/appearance/search-by-description"
    if token:
        form_data = {
            "session": settings.SESSION_TOKEN,
            "queryType": "CONTINUE",
            "token": token
        }
    else:
        form_data = {
            "session": settings.SESSION_TOKEN,
            "queryType": "TIME_RANGE",
            "queryDescriptors": query_descriptors,
            "from": from_time,
            "to": to_time,
            "cameraIds": camera_ids,
            "limit": limit,
            "scanType": scan_type
        }
    return await _make_appearance_search_request(url, form_data)

async def _fetch_and_encode_image(camera_id: str, timestamp: str) -> Optional[str]:
    """Fetches an image for a given camera and timestamp, and returns it as a Base64 string."""
    media_resp = await get_media_service(camera_id, timestamp, IMAGE_FORMAT)
    if media_resp and media_resp.status_code == 200:
        return base64.b64encode(media_resp.content).decode("utf-8")
    logger.warning(f"Failed to fetch image for camera {camera_id} at {timestamp}. Status: {media_resp.status_code if media_resp else 'N/A'}")
    return None

async def _process_appearance_item(item: Dict[str, Any], site_name: str) -> Dict[str, Any]:
    """Transforms a raw appearance item and fetches its image."""
    flat_item = item.copy()
    flat_item["cameraId"] = flat_item.pop("deviceGid", None)
    flat_item["eventStartTime"] = flat_item.pop("timestamp", None)
    flat_item["eventEndTime"] = flat_item.pop("endTimestamp", None)
    flat_item["siteName"] = site_name
    
    snapshots = flat_item.get("snapshots", [])
    face_timestamp = snapshots[0].get("timestamp") if snapshots else None

    if face_timestamp and flat_item["cameraId"]:
        # This will be run concurrently via asyncio.gather in the main function
        flat_item["imageBaseString"] = await _fetch_and_encode_image(flat_item["cameraId"], face_timestamp)
    
    return flat_item

async def fetch_all_face_events(from_time: str, to_time: str):
    # 1. Fetch initial data concurrently for better performance
    cameras_resp_task = asyncio.create_task(get_cameras_service())
    sites_resp_task = asyncio.create_task(get_sites_service())
    descriptions_resp_task = asyncio.create_task(get_appearance_descriptions_service())

    cameras_resp, sites_resp, descriptions_resp = await asyncio.gather(
        cameras_resp_task, sites_resp_task, descriptions_resp_task
    )

    # 2. Robustly extract data with error checking
    if not (cameras_resp and cameras_resp.status_code == 200):
        logger.error("Failed to fetch cameras, aborting face event fetch.")
        return {"total_length": 0, "results": []}
    cameras_data = cameras_resp.json()
    camera_ids = [cam["id"] for cam in cameras_data.get("result", {}).get("cameras", []) if "id" in cam]

    if not (sites_resp and sites_resp.status_code == 200):
        logger.error("Failed to fetch sites, aborting face event fetch.")
        return {"total_length": 0, "results": []}
    sites_data = sites_resp.json()
    sites = sites_data.get("result", {}).get("sites", [])
    if not sites:
        logger.error("No sites found, cannot determine site name.")
        return {"total_length": 0, "results": []}
    site_name = sites[0].get("name")

    if not (descriptions_resp and descriptions_resp.status_code == 200):
        logger.error("Failed to fetch appearance descriptions, aborting face event fetch.")
        return {"total_length": 0, "results": []}
    descriptions_data = descriptions_resp.json()
    
    # 3. Prepare search queries
    all_descriptors = descriptions_data.get("result", [])
    base_descriptors = [
        desc for desc in all_descriptors 
        if not desc.get("facet", "").startswith(VEHICLE_PREFIX) and desc.get("facet", "") != FACET_GENDER
    ]
    gender_descriptors = [
        [{"facet": FACET_GENDER, "tag": TAG_MALE}] + base_descriptors,
        [{"facet": FACET_GENDER, "tag": TAG_FEMALE}] + base_descriptors
    ]
    
    # 4. Execute searches and process results
    flat_results = []
    for query_descriptors in gender_descriptors:
        token = None
        resp = await search_by_description_service(from_time=from_time, to_time=to_time, query_descriptors=query_descriptors, camera_ids=camera_ids, limit=100)
        
        while resp and resp.status_code == 200:
            data = resp.json()
            results_on_page = data.get("result", {}).get("results", [])
            token = data.get("result", {}).get("token")

            if results_on_page:
                # Process all items on the current page concurrently for massive speedup
                processing_tasks = [_process_appearance_item(item, site_name) for item in results_on_page]
                processed_items = await asyncio.gather(*processing_tasks)
                flat_results.extend(processed_items)

            if token: resp = await search_by_description_service(token=token)
            else: break

    total_length = len(flat_results)
    logger.info(f"Completed fetching all face events. Total results: {total_length}")
    return {"total_length": total_length, "results": flat_results}
