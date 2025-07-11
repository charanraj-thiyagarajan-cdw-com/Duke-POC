from typing import Optional
from fastapi import APIRouter, Response, Query
from app.services.events_api import get_active_events_service, search_events_service, get_continue_events_service
from app.services.media_api import get_media_service
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger("avigilon-device-events")

@router.get("/api/events-search", response_class=Response)
async def events_search(
    query_type: str,
    serverId: Optional[str] = Query(None),
    from_time: Optional[str] = Query(None),
    to_time: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
    limit: int = 50,
    eventTopics: str = "ALL",
):
    try:
        if(query_type=="ACTIVE"):
            events_resp = await get_active_events_service(
                server_id=serverId,
                limit=limit
            )
        elif(query_type=="CONTINUE"):
            events_resp = await get_continue_events_service(token)
        else:
            events_resp = await search_events_service(
                from_time=from_time,
                to_time=to_time,
                server_id=serverId,
                limit=limit,
                event_topics=eventTopics
            )
        if not events_resp or events_resp.status_code != 200:
            logger.error(f"Failed to fetch events: {events_resp.text if events_resp else 'No response'}")
            return Response(content="{}", status_code=503, media_type="application/json")
        return Response(content=events_resp.text, status_code=200, media_type="application/json")
    except Exception as e:
        logger.error(f"Exception in events_search: {e}")
        return Response(content="{}", status_code=500, media_type="application/json")

@router.get("/api/media", response_class=Response)
async def media(
    cameraId: str,
    t: str,
    format: Optional[str] = Query("fmp4")
):
    try:
        media_resp = await get_media_service(camera_id=cameraId, t=t, format=format)
        if not media_resp or media_resp.status_code != 200:
            logger.error(f"Failed to fetch media: {media_resp.text if media_resp else 'No response'}")
            return Response(content="{}", status_code=503, media_type="application/json")
        return Response(content=media_resp.content, status_code=200, media_type="video/mp4")
    except Exception as e:
        logger.error(f"Exception in media: {e}")
        return Response(content="{}", status_code=500, media_type="application/json")

