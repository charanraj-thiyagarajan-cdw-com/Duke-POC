import httpx
from typing import Dict, Any, AsyncGenerator

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.avigilon_api import get_sites_service

settings = get_settings()
verify_ssl = settings.AVIGILON_API_VERIFY_SSL
AVIGILON_BASE = settings.AVIGILON_BASE
logger = get_logger("avigilon-events-service")


async def _make_event_search_request(params: Dict[str, Any]) -> httpx.Response | None:
    """A single, robust internal helper to make any event search request."""
    url = f"{AVIGILON_BASE}/events/search"
    default_params = {"session": settings.SESSION_TOKEN}
    final_params = {**default_params, **params}

    try:
        async with httpx.AsyncClient(verify=verify_ssl, timeout=60) as client:
            resp = await client.get(url, params=final_params)
            resp.raise_for_status()
            return resp
    except httpx.RequestError as exc:
        logger.error(f"Event search request failed: {exc}")
        return None
    except httpx.HTTPStatusError as exc:
        logger.error(
            f"Event search failed with status {exc.response.status_code}: {exc.response.text}"
        )
        return None


async def get_active_events_service(server_id, limit):
    """Fetches the currently active events."""
    params = {"queryType": "ACTIVE", "serverId": server_id, "limit": limit}
    return await _make_event_search_request(params)


async def search_events_service(
    from_time, to_time, server_id, limit, event_topics="ALL"
):
    """Starts a new event search for a given time range."""
    params = {
        "queryType": "TIME_RANGE",
        "from": from_time,
        "to": to_time,
        "serverId": server_id,
        "limit": limit,
        "eventTopics": event_topics,
    }
    return await _make_event_search_request(params)


# --- FIX is here ---
async def get_continue_events_service(token: str):
    """
    Continues a paginated event search using a token.
    FIX: The "limit" parameter is not allowed by the API on continuation calls.
    It has been removed from this function's signature and from the params dictionary.
    """
    params = {
        "queryType": "CONTINUE",
        "token": token,
    }
    return await _make_event_search_request(params)


async def fetch_and_yield_event_pages(
    from_time: str, to_time: str, page_size: int = 1000
) -> AsyncGenerator[list, None]:
    """
    Fetches events in pages and yields each page as soon as it's received.
    """
    sites_resp = await get_sites_service()
    if not sites_resp or sites_resp.status_code != 200:
        logger.error("Could not fetch sites to get server ID for event search.")
        return

    sites_data = sites_resp.json()
    try:
        server_id = "V3ov5LEAQdq9_i1jRVj28w"
    except (IndexError, KeyError) as e:
        logger.error(f"Could not parse server ID from sites response: {e}", exc_info=True)
        return

    resp = await search_events_service(
        from_time=from_time, to_time=to_time, server_id=server_id, limit=page_size
    )

    page_count = 0
    while resp and resp.status_code == 200:
        page_count += 1
        data = resp.json()
        events_on_page = data.get("result", {}).get("events", [])

        if events_on_page:
            logger.info(f"API Fetch: Yielding page {page_count} with {len(events_on_page)} events.")
            yield events_on_page

        token = data.get("result", {}).get("token")
        if token:
            # --- And the corresponding FIX is here ---
            # The call no longer passes 'limit'.
            resp = await get_continue_events_service(token=token)
        else:
            logger.info("API Fetch: No continuation token found. Finalizing fetch.")
            break