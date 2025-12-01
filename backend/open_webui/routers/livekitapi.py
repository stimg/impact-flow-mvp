import logging
import os
import uuid

from fastapi import (
    APIRouter,
    HTTPException,
)

from open_webui.env import SRC_LOG_LEVELS
from livekit import api

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()

LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET')
LIVEKIT_URL = os.getenv('LIVEKIT_URL')

@router.post("/token")
async def get_token(session_id: str = None):
    """
    Generate a LiveKit access token for joining a room.

    Args:
        session_id: Optional session ID to use for room naming.
                   If provided, ensures all components join the same room.
    """
    if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        raise HTTPException(status_code=400, detail="LiveKit is not configured on the server")

    identity = f"user-{uuid.uuid4().hex[:8]}"

    # CRITICAL: Use session_id to ensure all participants join the SAME room
    # This ensures frontend, backend, and voice-agent are in the same room
    if session_id:
        room = f"if-{session_id}"
        log.info(f"LiveKit token requested for session {session_id}, room: {room}")
    else:
        # Fallback to random room (not recommended for production)
        room = f"if-{uuid.uuid4().hex[:8]}"
        log.warning(f"LiveKit token requested without session_id, using random room: {room}")

    token = api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET) \
        .with_identity(identity) \
        .with_name("Impact Flow") \
        .with_grants(api.VideoGrants(
        room_join=True,
        room=room,
    )).to_jwt()

    return {
        "url": LIVEKIT_URL,
        "token": token,
        "room": room  # Return room name so frontend knows which room it joined
    }
