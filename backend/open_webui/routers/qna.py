import logging
import uuid

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

import tiktoken

from langchain.text_splitter import RecursiveCharacterTextSplitter, TokenTextSplitter

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.config import RAG_EMBEDDING_CONTENT_PREFIX
from open_webui.retrieval.utils import get_embedding_function
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.models.qna import QNAModel, ProcessQNAForm
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models
from open_webui.models.qna import ProcessQNAForm
from open_webui.retrieval.vector.dbs.pgvector import QNASchema

from open_webui.routers.recommendations import string_to_array

from open_webui.models.qna import get_qna_by_embedding
from open_webui.retrieval.functions.utils import get_embeddings

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


@router.get("/", response_model=Optional[QNAModel])
def find_by_question(request: Request, question: str, user=Depends(get_verified_user)):
    print("Question:", question)
    embedding = get_embeddings(request, [question], user)
    qna = get_qna_by_embedding(embedding[0], "q_embedding") if len(embedding) > 0 else None

    if qna and user.role == "admin":
        print("QNA:", qna)
        return qna

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ERROR_MESSAGES.NOT_FOUND,
    )


@router.post("/process")
def process_qna(
        request: Request,
        form_data: ProcessQNAForm,
        user=Depends(get_verified_user),
):
    # Generate UUID for the new qna
    id = form_data.id or uuid.uuid4()

    result = save_qna_to_vector_db(request, id, form_data.metadata, overwrite=True, split=False, user=user)
    if result:
        return {
            "status": True
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(),
        )


def save_qna_to_vector_db(
        request: Request,
        id,
        data: Optional[dict] = None,
        overwrite: bool = False,
        split: bool = True,
        add: bool = False,
        user = None,
) -> bool:
    # Check if entries with the same hash (metadata.hash) already exist
    if split:
        if request.app.state.config.TEXT_SPLITTER in ["", "character"]:
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
        elif request.app.state.config.TEXT_SPLITTER == "token":
            log.info(
                f"Using token text splitter: {request.app.state.config.TIKTOKEN_ENCODING_NAME}"
            )

            tiktoken.get_encoding(str(request.app.state.config.TIKTOKEN_ENCODING_NAME))
            text_splitter = TokenTextSplitter(
                encoding_name=str(request.app.state.config.TIKTOKEN_ENCODING_NAME),
                chunk_size=request.app.state.config.CHUNK_SIZE,
                chunk_overlap=request.app.state.config.CHUNK_OVERLAP,
                add_start_index=True,
            )
        else:
            raise ValueError(ERROR_MESSAGES.DEFAULT("Invalid text splitter"))

        docs = text_splitter.split_documents(docs)

    try:
        if VECTOR_DB_CLIENT.has_qna(qna_id=id):
            log.info(f"qna id {id} already exists")
            print(f"Overwrite {overwrite}")

            if overwrite:
                VECTOR_DB_CLIENT.delete_qna(id=id)
                log.info(f"deleting existing qna {id}")
            elif add is False:
                log.info(
                    f"qna {id} already exists, overwrite is False and add is False"
                )
                return True

        log.info(f"adding to qna {id}")

        texts = [
            data["question"],
            data["answer"],
        ]

        embeddings = get_embeddings(request, texts, user)

        VECTOR_DB_CLIENT.insert_qna(
            QNASchema(
                id=id,
                question_text=data["question"],
                answer_text=data["answer"],
                hint=data["hint"],
                q_embedding=embeddings[0],
                a_embedding=embeddings[1],
            )
        )

        return True

    except Exception as e:
        log.exception(e)
        raise e

