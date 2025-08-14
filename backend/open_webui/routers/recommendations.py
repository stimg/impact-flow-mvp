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
from open_webui.models.recommendations import RecommendationModel, ProcessRecommendationForm, Recommendation
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models
from open_webui.models.recommendations import ProcessRecommendationForm
from open_webui.retrieval.vector.dbs.pgvector import RecommendationSchema

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


@router.get("/", response_model=Optional[RecommendationModel])
def find_by_tag(tag: str, user=Depends(get_verified_user)):
    print("Tag:", tag)
    rec = Recommendation.find_by_tag(tag)

    print("Found recommendation:", rec)
    return rec


@router.post("/process")
def recommendation(
        request: Request,
        form_data: ProcessRecommendationForm,
        user=Depends(get_verified_user),
):
    # Generate UUID for the new recommendation if empty
    id = form_data.id or uuid.uuid4()

    # Normalize form data
    info = form_data.metadata["info"]
    data = {
        "tags": cleanup_csv(form_data.metadata["tags"]),
        "recommended": cleanup_csv(form_data.metadata["recommended"]),
        "suitable": cleanup_csv(form_data.metadata["suitable"]),
        "info": info,
    }

    docs = [
        Document(page_content=normalize_tags(form_data.metadata["tags"])),
        Document(page_content=info),
    ]

    result = save_recommendation_to_vector_db(request, id, docs, data, overwrite=True, split=False, user=user)
    if result:
        return {
            "status": True
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(),
        )


def save_recommendation_to_vector_db(
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

    def string_to_array(s: str) -> list:
        return [item.strip().lower() for item in s.split(",") if item.strip()]

    # Extract content for all documents
    texts = [doc.page_content for doc in docs]

    try:
        if VECTOR_DB_CLIENT.has_recommendation(rec_id=id):
            log.info(f"recommendation id {id} already exists")
            print(f"Overwrite {overwrite}")

            if overwrite:
                VECTOR_DB_CLIENT.delete_recommendation(id=id)
                log.info(f"deleting existing recommendation {id}")
            elif add is False:
                log.info(
                    f"recommendation {id} already exists, overwrite is False and add is False"
                )
                return True

        log.info(f"adding to recommendations {id}")
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

        # Generate embeddings for tag, answer, and tags
        embeddings = embedding_function(
            list(map(lambda x: x.replace("\n", " "), texts)),
            prefix='',
            user=user,
        )


        VECTOR_DB_CLIENT.insert_recommendation(
            RecommendationSchema(
                id=id,
                tags=data["tags"],
                recommended=data["recommended"],
                suitable=data["suitable"],
                info=data["info"],
                vec_tags=embeddings[0],
                vec_info=embeddings[1],
            )
        )
        return True

    except Exception as e:
        log.exception(e)
        raise e


def string_to_array(s: str) -> list[str]:
    seen = set()
    arr = []
    for item in s.split(","):
        tag = item.strip()
        if tag and tag not in seen:
            arr.append(tag)
            seen.add(tag)
    return arr


def normalize_tags(tags: str) -> str:
    return ", ".join(string_to_array(tags)).lower()

def cleanup_csv(s: str) -> str:
    return ", ".join(string_to_array(s))




