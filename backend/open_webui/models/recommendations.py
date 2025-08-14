import re
from typing import Optional, Dict, Union
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

class ProcessRecommendationForm(BaseModel):
    id: str
    metadata: Dict[str, Union[str, int, bool]]


class RecommendationClass:

    def find_by_tag(self, tag: str) -> Dict[str, str] or None:
        print(f"Searching for recommendation with tag: {tag}")
        rec_id = self.get_id_by_tag(tag)
        recommendation = self.get_recommendation_by_id(rec_id)

        return {
            "id": rec_id,
            "tags": recommendation.tags,
            "recommended": recommendation.recommended,
            "suitable": recommendation.suitable,
            "info": recommendation.info,
        }

    def get_id_by_tag(self, tag: str) -> str:
        tag_vector = generate_ollama_batch_embeddings("bge-m3", tag, OLLAMA_BASE_URL)[0]

        with get_db() as db:
            uuid_tuple = (db.query(RecommendationSchema.id)
                          .order_by(RecommendationSchema.vec_tags.l2_distance(tag_vector))
                          .limit(1)
                          .first())

            return str(uuid_tuple[0])


    def get_recommendation_by_id(self, id: str) -> Optional[RecommendationSchema]:
        try:
            with get_db() as db:
                return db.query(RecommendationSchema).filter_by(id=id).first()

        except Exception as e:
            print(f"Error fetching Recommendation: {e}")
            return None

Recommendation = RecommendationClass()
