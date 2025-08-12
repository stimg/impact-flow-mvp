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

from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter, TokenTextSplitter

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.config import RAG_EMBEDDING_CONTENT_PREFIX
from open_webui.retrieval.utils import get_embedding_function
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.models.qna import QNAModel, ProcessQNAForm, QNA
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models
from open_webui.models.qna import ProcessQNAForm
from open_webui.retrieval.vector.dbs.pgvector import QNASchema

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


@router.get("/", response_model=Optional[QNAModel])
def find_by_question(question: str, user=Depends(get_verified_user)):
    print("Question:", question)
    qna = QNA.find_by_question(question)
    print("QNA:", qna)
    if qna and user.role == "admin":
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
    # IMPORTANT: We pass all qna sections as JSON in the metadata field
    # not as text in the content field. This allows us to extract qna sections.

    # Generate UUID for the new qna
    id = form_data.id or uuid.uuid4()

    # Extract section names and contents
    docs = [
        Document(page_content=form_data.metadata["question"]),
        Document(page_content=form_data.metadata["answer"]),
        Document(page_content=form_data.metadata["tags"]),
    ]

    result = save_qna_to_vector_db(request, id, docs, form_data.metadata, overwrite=True, split=False, user=user)
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
        docs,
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

    if len(docs) == 0:
        raise ValueError(ERROR_MESSAGES.EMPTY_CONTENT)

    # Extract content for all documents
    texts = [doc.page_content for doc in docs]

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
        embedding_function = get_embedding_function(
            request.app.state.config.RAG_EMBEDDING_ENGINE,
            request.app.state.config.RAG_EMBEDDING_MODEL,
            request.app.state.ef,
            (
                request.app.state.config.RAG_OPENAI_API_BASE_URL
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else (
                    request.app.state.config.RAG_OLLAMA_BASE_URL
                    if request.app.state.config.RAG_EMBEDDING_ENGINE == "ollama"
                    else request.app.state.config.RAG_AZURE_OPENAI_BASE_URL
                )
            ),
            (
                request.app.state.config.RAG_OPENAI_API_KEY
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "openai"
                else (
                    request.app.state.config.RAG_OLLAMA_API_KEY
                    if request.app.state.config.RAG_EMBEDDING_ENGINE == "ollama"
                    else request.app.state.config.RAG_AZURE_OPENAI_API_KEY
                )
            ),
            request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
            azure_api_version=(
                request.app.state.config.RAG_AZURE_OPENAI_API_VERSION
                if request.app.state.config.RAG_EMBEDDING_ENGINE == "azure_openai"
                else None
            ),
        )

        # Generate embeddings for question, answer, and tags
        embeddings = embedding_function(
            list(map(lambda x: x.replace("\n", " "), texts)),
            prefix='',
            user=user,
        )

        VECTOR_DB_CLIENT.insert_qna(
            QNASchema(
                id=id,
                scope=data["scope"],
                question_text=data["question"],
                answer_text=data["answer"],
                tags_text=data["tags"],
                q_embedding=embeddings[0],
                a_embedding=embeddings[1],
                t_embedding=embeddings[2],
            )
        )

        # VECTOR_DB_CLIENT.insert_qna({
        #     "id": id,
        #     "question_text": data["question"],
        #     "answer_text": data["answer"],
        #     "tags_text": data["tags"],
        #     "q_embedding": embeddings[0],
        #     "a_embedding": embeddings[1],
        #     "t_embedding": embeddings[2],
        # })
        #
        return True

    except Exception as e:
        log.exception(e)
        raise e

