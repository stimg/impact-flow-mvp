from typing import List
import re
import html
import psycopg2
import requests
import random
from fastapi import (
    Depends,
    Request,
)
from open_webui.internal.db import get_db
from open_webui.retrieval.utils import get_embedding_function
from open_webui.utils.auth import get_verified_user
from psycopg2.extras import RealDictCursor
from sqlalchemy import text

from open_webui.retrieval.functions.data import questions, mentora_hints


def get_user_name_from_full_name(self, username: str | None) -> str:
    if not username:
        return ""

    name_regex = r"^(.+?)(?=\s+(?:von(?:\s+(?:der|den|dem))?|van(?:\s+(?:der|den))?|zu|zur|zum|vom|de|del|du)\b|\s+\S+$)"
    match = re.match(name_regex, username or "")
    return match.group(1) if match else ""

def sanitize_user_input(text: str, strict: bool = True) -> str:
    clean = text
    re_html_tags        = re.compile(r"</?[^>]+(?:>|$)")
    re_md_link_or_image = re.compile(r"!?\[([^\]]*?)\]\([^)]+?\)")
    re_md_inline_fmt    = re.compile(r"[*~`>#]+")
    re_unescape_bslash  = re.compile(r"\\([\\`*_{[}()\#+\-.!])")
    re_control_chars = re.compile(r"[\u0000-\u001F\u007F-\u009F]")
    re_space_before_nl  = re.compile(r"\s+\n")

    # Strict Mode Regex: erlaubt nur Buchstaben, Ziffern, Satzzeichen, Whitespace
    # Satzzeichen: . , ; : ! ? ( ) - ' " … und Leerzeichen/Tab/Zeilenumbruch
    re_strict = re.compile(r"[^a-zA-Z0-9äöüÄÖÜß& .,;:!?()'\"\-\n\r\t]")


# 1) HTML-Tags entfernen
    clean = re_html_tags.sub("", clean)

    # 2) Markdown-Links/Images entfernen (nur Anzeigetext behalten)
    clean = re_md_link_or_image.sub(r"\1", clean)

    # 3) Einfache Markdown-Formatierungen entfernen
    clean = re_md_inline_fmt.sub("", clean)

    # 4) Backslashes vor Sonderzeichen auflösen
    # clean = re_unescape_bslash.sub(r"\1", clean)

    # 5) HTML-Entities dekodieren
    clean = html.unescape(clean)

    # 6) Steuerzeichen entfernen (außer \n, \r, \t)
    clean = re_control_chars.sub("", clean)

    # 7) Whitespace normalisieren
    clean = re_space_before_nl.sub("\n", clean).strip()

    # 8) Strict-Filter anwenden (optional)
    if strict:
        clean = re_strict.sub("", clean)

    return clean.replace("ß", "ss")

def get_embedding(self, text=""):
    response = self.embedding.embeddings.create(
        model=self.valves.EMBEDDING_MODEL_ID,
        input=text or "EMPTY_QUERY_SENTINEL",
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
    model = request.app.state.config.RAG_EMBEDDING_MODEL

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
                request.app.state.config.RAG_OLLAMA_API_KEY
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

def get_follow_ups(model: str, func: str, count=3):
    # print(f"----> get_follow_ups: {model}, {func}, {count}")
    model_map = {
        "empfehlungsregister_agent": "recommendations",
        "agent_openai": "chat",
        "mentora": "chat",
    }
    func_map = {
        "get_product_list": "categories",
        "get_category_list": "categories",
        "get_products_by_category": "by_category",
        "get_products_by_property": "by_property",
        "get_product_details": "properties",
        "get_product_property": "properties",
        "get_qna_answer": "qna"
    }
    topic = model_map.get(model, "")
    section = func_map.get(func, "")

    # print(f"----> topic: {topic}, section: {section}")
    if not topic in questions:
        return []

    if topic == "recommendations":
        question_set = questions[topic]
    elif section:
        question_set = questions[topic][section]
    else:
        return []

    qn = len(question_set)

    if qn < count:
        return []

    # Generate random questions using list comprehension
    follow_ups = random.sample(question_set, count)

    return follow_ups

def parse_template(tpl: str, cols: List[str], data: dict):
    for col in cols:
        # print(f"---> col: {col} ({col.upper()})")
        # print(f"---> data[col]: {data[col]}")
        if col == "hint":
            hl = len(mentora_hints)
            hint = data["hint"] or mentora_hints[random.randrange(hl)]
            tpl = tpl.replace("{{MENTORA_PRO_HINT}}", hint)
        else:
            tpl = tpl.replace(f"{{{{{col.upper()}}}}}", data[col])

    # print(f"PARSED TEMPLATE: {tpl}")

    return tpl

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
    return ",".join(string_to_array(tags)).lower()

def cleanup_csv(s: str) -> str:
    return ", ".join(string_to_array(s))
