import re
from typing import Optional, Dict, Union, List
from pydantic import BaseModel, UUID4

from open_webui.config import OLLAMA_BASE_URL
from open_webui.internal.db import Base, get_db
from open_webui.retrieval.utils import generate_ollama_batch_embeddings
from open_webui.retrieval.vector.dbs.pgvector import QNASchema


####################
# Forms
####################


class QNAModel(BaseModel):
    id: UUID4
    question: str
    answer: str
    hint: str

class ProcessQNAForm(BaseModel):
    id: str
    metadata: Dict[str, Union[str, int, bool]]


def get_qna_by_embedding(vec: List[float], col: str):
    embedding_column = getattr(QNASchema, col)

    with get_db() as db:
        qna = (db.query(QNASchema)
          .order_by(embedding_column.l2_distance(vec))
          .limit(1)
          .first())

    return {
        "id": str(qna.id),
        "question": qna.question_text,
        "answer": qna.answer_text,
        "hint": qna.hint or '',
    } if qna else None

