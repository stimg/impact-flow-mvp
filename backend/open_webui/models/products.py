import re
from typing import Optional, Dict, Union

from open_webui.config import OLLAMA_BASE_URL
from open_webui.internal.db import Base, get_db
from open_webui.models.tags import TagModel, Tag, Tags
from open_webui.retrieval.utils import generate_ollama_batch_embeddings
from pgvector.sqlalchemy import Vector
from pydantic import BaseModel, UUID4
from sqlalchemy import Column, Text, UUID
from sqlalchemy.dialects.postgresql import JSONB


######################
# Product DB Schema
######################

class ProductChunk(Base):
    __tablename__ = 'product_chunks'
    chunk_id = Column(UUID, primary_key=True)
    product_id = Column(UUID)
    chunk_text = Column(Text)
    embedding = Column(Vector(1024))
    vmetadata = Column(JSONB)


class QNA(Base):
    __tablename__ = 'q_and_a'
    id = Column(UUID, primary_key=True)
    question_text = Column(Text)
    answer_text = Column(Text)
    q_embedding = Column(Vector(1024))
    a_embedding = Column(Vector(1024))
    vmetadata = Column(JSONB)


####################
# Forms
####################


class ProductModel(BaseModel):
    id: UUID4
    name: str
    tags: str
    categories: str
    short_description: str
    similar_products: Optional[str] = None
    recommended_products: Optional[str] = None
    supporting_products: Optional[str] = None
    combinable_with: Optional[str] = None
    product_details: Optional[str] = None
    target_audience: Optional[str] = None
    ingredients: Optional[str] = None
    intake_recommendation: Optional[str] = None
    reference_link: Optional[str] = None
    application_area: Optional[str] = None
    user_experience: Optional[str] = None
    formulation_origin: Optional[str] = None
    history: Optional[str] = None


class ProcessProductForm(BaseModel):
    id: str
    content: str
    metadata: Optional[Dict[str, Union[str, int, bool]]] = None
    overwrite: bool = False


class ImpactFlowProducts:

    def find_by_name(self, product_name: str) -> Dict[str, str] or None:
        id = self.get_id_by_name(product_name)
        product_chunks = self.get_chunks_by_id(id)

        product = {
            chunk.vmetadata.get("section"): re.sub(r"^.*:\s", "", chunk.chunk_text)
            for chunk in product_chunks
        }
        product["id"] = id

        return product

    def get_id_by_name(self, product_name: str) -> str:
        product_name_vector = generate_ollama_batch_embeddings("bge-m3", product_name, OLLAMA_BASE_URL)[0]

        with get_db() as db:
            uuid_tuple = (db.query(ProductChunk.product_id)
                .filter(ProductChunk.vmetadata['section'].astext == 'name')
                .order_by(ProductChunk.embedding.l2_distance(product_name_vector))
                .limit(1)
                .first())

            return str(uuid_tuple[0])


    def get_chunks_by_id(self, product_id: str) -> list[ProductChunk]:
        with get_db() as db:
            return [
                chunk
                for chunk in db.query(ProductChunk).filter_by(product_id=product_id).all()
            ]


Products = ImpactFlowProducts()
