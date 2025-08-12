import re
from typing import Optional, Dict, Union
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
    scope: str
    question: str
    answer: str
    tags: str

class ProcessQNAForm(BaseModel):
    id: str
    metadata: Dict[str, Union[str, int, bool]]


class QNAClass:

    def find_by_question(self, question: str) -> Dict[str, str] or None:
        print(f"Searching for Q&A related to: {question}")
        id = self.get_id_by_question(question)
        qna = self.get_qna_by_id(id)

        return {
            "id": id,
            "scope": qna.scope,
            "question": qna.question_text,
            "answer": qna.answer_text,
            "tags": qna.tags_text,
        }

    def get_id_by_question(self, question: str) -> str:
        question_vector = generate_ollama_batch_embeddings("bge-m3", question, OLLAMA_BASE_URL)[0]

        with get_db() as db:
            uuid_tuple = (db.query(QNASchema.id)
                          .order_by(QNASchema.q_embedding.l2_distance(question_vector))
                          .limit(1)
                          .first())

            return str(uuid_tuple[0])


    def get_qna_by_id(self, id: str) -> Optional[QNASchema]:
        try:
            with get_db() as db:
                return db.query(QNASchema).filter_by(id=id).first()

        except Exception as e:
            print(f"Error fetching QNA: {e}")
            return None


QNA = QNAClass()
