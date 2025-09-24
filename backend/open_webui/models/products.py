import re
from typing import Optional, Dict, Union, List
from pydantic import BaseModel, UUID4

from open_webui.config import OLLAMA_BASE_URL
from open_webui.internal.db import Base, get_db
from open_webui.models.tags import TagModel, Tag, Tags
from open_webui.retrieval.utils import generate_ollama_batch_embeddings, generate_openai_batch_embeddings
from open_webui.retrieval.vector.dbs.pgvector import ProductChunk
from open_webui.retrieval.functions.utils import get_id_by_embedding


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
    hint: Optional[str] = None


class ProcessProductForm(BaseModel):
    id: str
    metadata: Optional[Dict[str, Union[str, int, bool]]] = None


def get_chunks_by_id(product_id: str) -> list[ProductChunk]:
    with get_db() as db:
        return [
            chunk
            for chunk in db.query(ProductChunk).filter_by(product_id=product_id).all()
        ]


def find_by_embedding(embedding: List[float], col="name") -> Dict[str, str] or None:
    id = get_id_by_embedding(embedding, col)
    print(f"Searching for product with id: {id}")
    product_chunks = get_chunks_by_id(id)

    product = {
        chunk.section: chunk.chunk_text
        for chunk in product_chunks
    }
    product["id"] = id
    print(f"Found product: {product}")

    return product
