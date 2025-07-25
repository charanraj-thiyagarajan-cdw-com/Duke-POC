import httpx
import time
import hashlib
from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()

AVIGILON_BASE = settings.AVIGILON_BASE #settings.AVIGILON_BASE
USERNAME = settings.AVIGILON_USERNAME
PASSWORD = settings.AVIGILON_PASSWORD
CLIENT_NAME = settings.AVIGILON_CLIENT_NAME
USER_NONCE = settings.AVIGILON_USER_NONCE
USER_KEY = settings.AVIGILON_USER_KEY

logger = get_logger("avigilon-auth")

def generate_auth_token():
    epoch = int(time.time())
    hash_input = f"{epoch}{USER_KEY}".encode('utf-8')
    hash_output = hashlib.sha256(hash_input).hexdigest()
    return f"{USER_NONCE}:{epoch}:{hash_output}"

async def authenticate():
    try:
        async with httpx.AsyncClient(verify=False, timeout=10) as client:
            response = await client.post(
                f"{AVIGILON_BASE}/login",
                json={"username": USERNAME, "password": PASSWORD, "clientName": CLIENT_NAME, "authorizationToken": generate_auth_token()},
                headers={"content-type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            json_response = response.json()
            settings.SESSION_TOKEN = json_response["result"]["session"]
            logger.info("Successfully authenticated with Avigilon API")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        raise