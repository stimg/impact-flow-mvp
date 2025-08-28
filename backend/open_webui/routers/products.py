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
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.models.products import ProductModel, ProcessProductForm, Products
from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models
from open_webui.retrieval.functions.utils import get_embeddings

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


@router.get("/", response_model=Optional[ProductModel])
def find_by_name(request: Request, product_name: str, section="name", user=Depends(get_verified_user)):
    print("Product Name:", product_name)
    embedding = get_embeddings(request, [product_name], user)
    product = Products.find_by_embedding(embedding[0], section) if len(embedding) > 0 else None

    if product and user.role == "admin":
        return product

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=ERROR_MESSAGES.NOT_FOUND,
    )


@router.post("/process")
def process_product(
    request: Request,
    form_data: ProcessProductForm,
    user=Depends(get_verified_user),
):
    # IMPORTANT: We pass all product sections as JSON in the metadata field
    # not as text in the content field. This allows us to extract product sections.

    # Generate UUID for the new product
    id = form_data.id or uuid.uuid4()

    # Create common metadata for all product sections
    metadata = {
        "name": form_data.metadata["name"],
        "reference_link": form_data.metadata["reference_link"],
        "source": form_data.metadata["source"],
        "created_by": user.id
    }

    result = save_product_to_vector_db(request, id, form_data.metadata, metadata, overwrite=True, split=False, user=user)
    if result:
        return {
            "status": True,
            "product_name": form_data.metadata["name"],
        }
    else:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ERROR_MESSAGES.DEFAULT(),
        )


def save_product_to_vector_db(
        request: Request,
        product_id,
        data: dict,
        metadata: Optional[dict] = None,
        overwrite: bool = False,
        split: bool = True,
        add: bool = False,
        user = None,
) -> bool:
    # Extract section names and contents
    texts = [data[section] for section in data]
    sections = list(data.keys())

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
        if VECTOR_DB_CLIENT.has_product(product_id=product_id):
            log.info(f"product id {product_id} already exists")
            print(f"Overwrite {overwrite}")

            if overwrite:
                VECTOR_DB_CLIENT.delete_product(product_id=product_id)
                log.info(f"deleting existing product {product_id}")
            elif add is False:
                log.info(
                    f"product {product_id} already exists, overwrite is False and add is False"
                )
                return True

        log.info(f"adding to product {product_id}")

        embeddings = get_embeddings(request, list(map(lambda x: x.replace("\n", " "), texts)), user)

        items = [
            {
                "chunk_id": str(uuid.uuid4()),
                "product_id": product_id,
                "section": sections[idx],
                "chunk_text": text,
                "embedding": embeddings[idx],
                "metadata": metadata,
            }
            for idx, text in enumerate(texts)
        ]

        VECTOR_DB_CLIENT.insert_product_chunks(
            product_id=product_id,
            items=items,
        )

        return True

    except Exception as e:
        log.exception(e)
        raise e

