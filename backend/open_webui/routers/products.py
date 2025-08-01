import logging
import random
import uuid

from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status, requests,
)

import tiktoken

from langchain_core.documents import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter, TokenTextSplitter

from open_webui.constants import ERROR_MESSAGES
from open_webui.env import SRC_LOG_LEVELS
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.config import RAG_EMBEDDING_CONTENT_PREFIX
from open_webui.models.users import Users
from open_webui.retrieval.utils import get_embedding_function
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.models.products import ProductModel, ProcessProductForm

from pydantic import BaseModel

from open_webui.env import ENABLE_FORWARD_USER_INFO_HEADERS
from open_webui.models.products import Products
from open_webui.routers.ollama import GenerateEmbedForm, get_api_key
from open_webui.utils.models import get_all_models

log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])


router = APIRouter()


@router.get("/", response_model=Optional[ProductModel])
def find_by_name(product_name: str, user=Depends(get_verified_user)):
    print("Product Name:", product_name)
    product = Products.find_by_name(product_name)

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

    # Extract section names and contents
    docs = [
        Document(
            page_content=form_data.metadata[section],
            # Local metadata for each section
            metadata = {
                "section": section
            }
        ) for section in form_data.metadata
    ]

    result = save_product_to_vector_db(request, id, docs, metadata, overwrite=True, split=False, user=user)
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


@router.post("/embeddings")
async def generateEmbedings(
        request: Request,
        form_data: GenerateEmbedForm,
        url_idx: Optional[int] = None,
        user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_batch_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    try:
        r = requests.request(
            method="POST",
            url=f"{url}/api/embed",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
                **(
                    {
                        "X-OpenWebUI-User-Name": user.name,
                        "X-OpenWebUI-User-Id": user.id,
                        "X-OpenWebUI-User-Email": user.email,
                        "X-OpenWebUI-User-Role": user.role,
                    }
                    if ENABLE_FORWARD_USER_INFO_HEADERS and user
                    else {}
                ),
            },
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


def save_product_to_vector_db(
        request: Request,
        product_id,
        docs,
        metadata: Optional[dict] = None,
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

    # Merge global metadata with the local document metadata
    # We pass local section info to each section chunk
    doc_metadata = [
        {
            **doc.metadata,
            **(metadata if metadata else {}),
        }
        for doc in docs
    ]

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

        embeddings = embedding_function(
            list(map(lambda x: x.replace("\n", " "), texts)),
            prefix=RAG_EMBEDDING_CONTENT_PREFIX,
            user=user,
        )

        items = [
            {
                "chunk_id": str(uuid.uuid4()),
                "product_id": product_id,
                "chunk_text": text,
                "embedding": embeddings[idx],
                "metadata": doc_metadata[idx],
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

