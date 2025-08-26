from typing import List

import psycopg2
import re
import requests

from fastapi import (
    Depends,
    Request,
)


from psycopg2.extras import RealDictCursor
from sqlalchemy import text

from open_webui.retrieval.utils import get_embedding_function
from open_webui.utils.auth import get_verified_user
from open_webui.internal.db import get_db


def get_user_name_from_full_name(self, username: str | None) -> str:
    if not username:
        return ""

    name_regex = r"^(.+?)(?=\s+(?:von(?:\s+(?:der|den|dem))?|van(?:\s+(?:der|den))?|zu|zur|zum|vom|de|del|du)\b|\s+\S+$)"
    match = re.match(name_regex, username or "")
    return match.group(1) if match else ""

def get_embedding(self, text=""):
    # Return zero vector on empty text
    if not text:
        return [] * 1024

    response = self.embedding.embeddings.create(
        model=self.valves.EMBEDDING_MODEL_ID,
        input=text,
    )

    return response.data[0].embedding

def generate_embedding(self, text):
    # Return zero vector on empty text
    if not text:
        return [] * 1024

    res = requests.request(
        method="POST",
        url=f"{self.valves.API_BASE_URL}/embed",
        headers={
            "Content-Type": "application/json",
        },
        json={
            "model": self.valves.EMBEDDING_MODEL_ID,
            "input": text,
            "options": {
                "num_ctx": 2048,
                "top_k": 3,
                "top_p": 0.3,
                "temperature": 0.3,
            },
        },
    )

    embeddings = res.json()["embeddings"]
    vector = embeddings[0] or []
    # print(f"Embedding: {vector}")

    return vector

def query_db(self, sql: str, fetch="one", params=None):
    """
    fetch: "one" | "all" | "val"
      - "one": return one row (dict or None)
      - "all": return list[dict]
      - "val": return first column of first row (or None)
    """
    try:
        with psycopg2.connect(
                host=self.valves.POSTGRES_HOST,
                port=self.valves.POSTGRES_PORT,
                user=self.valves.POSTGRES_USER,
                password=self.valves.POSTGRES_PASSWORD,
                database=self.valves.POSTGRES_DATABASE,
        ) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                if fetch == "all":
                    rows = cur.fetchall()
                    return rows
                row = cur.fetchone()
                if fetch == "val":
                    return None if row is None else next(iter(row.values()))
                return row  # dict or None

    except Exception as e:
        # Prefer raising; caller decides how to handle
        raise


def get_embeddings(request: Request, texts: list, user=Depends(get_verified_user)):
    engine = request.app.state.config.RAG_EMBEDDING_ENGINE
    model =  request.app.state.config.RAG_EMBEDDING_MODEL

    embedding_function = get_embedding_function(
        engine,
        model,
        request.app.state.ef,
        (
            request.app.state.config.RAG_OPENAI_API_BASE_URL
            if engine == "openai"
            else (
                request.app.state.config.RAG_OLLAMA_BASE_URL
                if engine == "ollama"
                else request.app.state.config.RAG_AZURE_OPENAI_BASE_URL
            )
        ),
        (
            request.app.state.config.RAG_OPENAI_API_KEY
            if engine == "openai"
            else (
                'ollama' # request.app.state.config.RAG_OLLAMA_API_KEY
                if engine == "ollama"
                else request.app.state.config.RAG_AZURE_OPENAI_API_KEY
            )
        ),
        request.app.state.config.RAG_EMBEDDING_BATCH_SIZE,
        azure_api_version=(
            request.app.state.config.RAG_AZURE_OPENAI_API_VERSION
            if engine == "azure_openai"
            else None
        ),
    )

    return embedding_function(
        list(map(lambda x: x.replace("\n", " "), texts)),
        prefix="",
        user=user,
    )


def get_id_by_embedding(vec: List[float], col: str) -> str:
    with get_db() as db:
        ### This SQLAlchemy approach doesn't work for an unknown reason
        # uuid_tuple = (db.query(ProductChunk.product_id)
        # .filter(ProductChunk.section == col) <--- this line doesn't work
        # .order_by(ProductChunk.embedding.l2_distance(vec))
        # .limit(1)
        # .first())

        uuid_tuple = db.execute(text("""
            SELECT product_id
            FROM product_chunks
            WHERE section = :col
            ORDER BY embedding <#> :vec
            LIMIT 1
            """), {"col": col, "vec": f"{vec}"}).first()

        return str(uuid_tuple[0])


