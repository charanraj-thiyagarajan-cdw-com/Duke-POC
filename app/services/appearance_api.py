import httpx
from app.core.config import get_settings
from app.core.logging import get_logger
from typing import Optional
from app.services.avigilon_api import get_cameras_service
from app.services.media_api import get_media_service
import base64
import numpy as np
import cv2
from deepface import DeepFace


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
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10) as client:
            resp = await client.post(url, json=form_data)
            return resp
    except httpx.RequestError as exc:
        logger.error(f"Appearance search failed: {exc}")
        return None

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
    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=10) as client:
            resp = await client.post(url, json=form_data)
            return resp
    except httpx.RequestError as exc:
        logger.error(f"Appearance search-by-description failed: {exc}")
        return None

async def fetch_all_face_events(from_time: str, to_time: str):
    cameras_resp = await get_cameras_service()
    cameras_data = cameras_resp.json()
    camera_ids = [cam["id"] for cam in cameras_data.get("result", {}).get("cameras", []) if "id" in cam]
    query_descriptors = [
        {"facet": "FACE_MASK_PRESENCE", "tag": "NOT_DETECTED"},
        {"facet": "FACE_MASK_PRESENCE", "tag": "DETECTED"}
    ]
    flat_results = []
    token = None
    resp = await search_by_description_service(
        from_time=from_time,
        to_time=to_time,
        query_descriptors=query_descriptors,
        camera_ids=camera_ids,
        limit=100
    )
    while resp and resp.status_code == 200:
        data = resp.json()
        results = data.get("result", {}).get("results", [])
        token = data.get("result", {}).get("token", None)
        for item in results:
            flat_item = item.copy()
            flat_item["cameraId"] = flat_item.pop("deviceGid")
            flat_item["eventStartTime"] = flat_item.pop("timestamp")
            flat_item["eventEndTime"] = flat_item.pop("endTimestamp")
            snapshots = flat_item.pop("snapshots", [])
            for snap in snapshots:
                if snap.get("type") == "APPEARANCE_SEARCH_SNAPSHOT_TYPE_FULL_OBJECT":
                    flat_item["objectROI"] = snap.get("roi")
                    flat_item["objectTimeStamp"] = snap.get("timestamp")
                if snap.get("type") == "APPEARANCE_SEARCH_SNAPSHOT_TYPE_FACE":
                    flat_item["faceROI"] = snap.get("roi")
                    flat_item["faceTimeStamp"] = snap.get("timestamp")
            media_resp = await get_media_service(flat_item["cameraId"], flat_item["faceTimeStamp"], "jpeg")
            image_base64 = base64.b64encode(media_resp.content).decode("utf-8")
            flat_item["imageBaseString"] = image_base64
            if image_base64:
                try:
                    image_bytes = base64.b64decode(image_base64)
                    np_arr = np.frombuffer(image_bytes, np.uint8)
                    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        faces = DeepFace.represent(img_path=img, enforce_detection=False, model_name="Facenet512")
                        embeddings = [face["embedding"] for face in faces]
                        flat_item["embeddings"] = embeddings
                except Exception as e:
                    logger.error(f"Face embedding fetch failed: {e}")
            flat_results.append(flat_item)
        if token:
            resp = await search_by_description_service(token=token)
        else:
            break
    total_length = len(flat_results)
    return {"total_length": total_length, "results": flat_results}
