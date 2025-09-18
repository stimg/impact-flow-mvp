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
from open_webui.models.recommendations import RecommendationModel, ProcessRecommendationForm
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models
from open_webui.models.recommendations import ProcessRecommendationForm
from open_webui.retrieval.vector.dbs.pgvector import RecommendationSchema
from open_webui.retrieval.functions.utils import (get_embeddings)
from open_webui.models.recommendations import get_recommendation_by_tag
from open_webui.retrieval.functions.utils import cleanup_csv, normalize_tags

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


@router.get("/", response_model=Optional[RecommendationModel])
def find_by_tag(tag: str, user=Depends(get_verified_user)):
    # We search recommendation by tag
    print("Tag:", tag)
    rec = get_recommendation_by_tag(tag) if tag else None

    if rec and user.role == "admin":
        print("Found recommendation:", rec)
        return rec

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ERROR_MESSAGES.NOT_FOUND,
    )



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
        "hint": form_data.metadata["hint"],
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

        embeddings = get_embeddings(request, texts, user)

        VECTOR_DB_CLIENT.insert_recommendation(
            RecommendationSchema(
                id=id,
                tags=data["tags"],
                recommended=data["recommended"],
                suitable=data["suitable"],
                info=data["info"],
                hint=data["hint"],
                vec_tags=embeddings[0],
                vec_info=embeddings[1],
            )
        )
        return True

    except Exception as e:
        log.exception(e)
        raise e

