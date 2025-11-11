import re
from typing import Optional, Dict, Union, List
from pydantic import BaseModel, UUID4

from open_webui.internal.db import Base, get_db
from open_webui.retrieval.vector.dbs.pgvector import RecommendationSchema
from sqlalchemy import func


####################
# Forms
####################

class LivekitTokenRequest(BaseModel):
    identity: Optional[str] = None
    start_transcription: Optional[bool] = True
    url: Optional[str] = None
    room: Optional[str] = None
    vendor: Optional[str] = None
    stt: Optional[str] = None
    language: Optional[str] = None


