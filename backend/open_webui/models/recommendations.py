import re
from typing import Optional, Dict, Union, List
from pydantic import BaseModel, UUID4

from open_webui.config import OLLAMA_BASE_URL
from open_webui.internal.db import Base, get_db
from open_webui.retrieval.utils import generate_ollama_batch_embeddings
from open_webui.retrieval.vector.dbs.pgvector import RecommendationSchema


####################
# Forms
####################


class RecommendationModel(BaseModel):
    id: UUID4
    tags: str
    recommended: str
    suitable: str
    info: str
    hint: str

def get_recommendation_by_embedding(vec: List[float]) -> Dict[str, str] or None:
    with get_db() as db:
        recommendation = (db.query(RecommendationSchema)
                      .order_by(RecommendationSchema.vec_tags.l2_distance(vec))
                      .limit(1)
                      .first())

        return {
            "id": str(recommendation.id),
            "tags": recommendation.tags,
            "recommended": recommendation.recommended,
            "suitable": recommendation.suitable,
            "info": recommendation.info,
            "hint": recommendation.hint or '',
        } if recommendation else None

class ProcessRecommendationForm(BaseModel):
    id: str
    metadata: Dict[str, Union[str, int, bool]]
