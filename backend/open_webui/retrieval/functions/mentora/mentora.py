import json
import psycopg2
import re
import time
from typing import Literal
from functools import partial

from openai import OpenAI
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field

from open_webui.retrieval.functions.utils import (
    query_db,
    get_user_name_from_full_name,
    get_embedding,
    sanitize_user_input,
)
from open_webui.retrieval.functions.data import product_names


class Pipe:
    class Valves(BaseModel):
        RAG_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model for RAG. Openrouter --> qwen-2.5, Novita --> qwen2.5 (!)",
        )
        TOOLS_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model for Tools. Openrouter --> qwen-2.5, Novita --> qwen2.5 (!)",
        )
        OPENAI_API_BASE_URL: Literal[
            "https://openrouter.ai/api/v1",
            "https://api.novita.ai/v3/openai",
            "https://api.openai.com/v1",
        ] = Field(
            default="https://api.novita.ai/v3/openai",
            description="OpenAI API URL.",
        )
        OPENAI_API_KEY: str = Field(
            default="",
            description="OpenAI API key.",
        )
        EMBEDDING_MODEL_ID: Literal[
            "baai/bge-m3",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="baai/bge-m3",
            description="Model to use for embedding generation.",
        )
        EMBEDDING_API_BASE_URL: Literal[
            "https://api.novita.ai/openai/v1",
            "https://api.openai.com/v1",
        ] = Field(
            default="https://api.novita.ai/openai/v1",
            description="OpenAI API URL.",
        )
        EMBEDDING_API_KEY: str = Field(
            default="",
            description="Embedding API key.",
        )

        PROMPT_LIST: str = Field(
            default="""
            INSTRUCTIONS:
            - Always use Markdown format.
            - List all the products from the list, keeping the order in the given list.
            - For each product, always render:
              1. Product name as the Markdown link. Take the product name from the JSON "name" property and the product link from the "reference_link" property.
              2. The em dash (–) surrounded by spaces.
              3. Product categories in cursive (*italic*).

            - Render every list entry exactly like in this example:

            [Burner](https://www.ethno-health.com/artikeldetail/product) – *Body & Clean*
            """,
            description="System prompt for product list.",
        )
        PROMPT_LIST_BY_PROPERTY: str = Field(
            default="""
            Your goals:
            1. Do not re-rank or filter. Assume the context is already filtered. Render all items.
            2. Render **all** products from CONTEXT, **in the same order**, with no omissions or additions.
            3. Language: **German only**.
            4. Use the exact output format in “Rendering”.

            Rendering:
            - For each product, always render:
              1. Product name as the Markdown link. Take the product name from the JSON "name" property and the product link from the "reference_link" property.
              2. The em dash (–) surrounded by spaces.
              3. Product categories in cursive (*italic*).
              4. The property text.

            - Render **every product exactly** like in this example:            
            [Burner](https://www.ethno-health.com/artikeldetail/product) – *Body & Clean*
            
            Das produkt ist speziell für Sportler entwickelt. Es hilft dabei, die Energie im Alltag 
            zu steigern und den sportlichen Leistungsgrad zu verbessern.

            """,
            description="System prompt for product list.",
        )
        PROMPT_CATEGORIES: str = Field(
            default="""
            INSTRUCTIONS:
            - Always use Markdown format.
            - List all categories. Don't use an unordered list format.
            - For each category render:
              1. Category name in **bold**.
              2. The em dash (–) surrounded by spaces.
              3. Product tags: comma-separated, in cursive (*italic*).

              - Render every category exactly like in this example:

              **Beauty & Lifestyle** – *Gewebe, Kollagenbildung, Haare, Muskeln, Haut, Nägel, Schönheit, Lifestyle*
            """,
            description="System prompt for product list.",
        )
        PROMPT_DETAILS: str = Field(
            default="""
                You MUST take the product name from the JSON "name" property and the product link from the "reference_link" property.
                You MUST ignore any URLs found in any other fields.
                Never invent or modify the URL or name.

                INSTRUCTIONS:
                - Always use Markdown format.
                - You must always create the following sections using the JSON object from the context:
                  1. Product name as the Markdown link.
                  2. On the same line, the em dash (–) surrounded by spaces.
                  3. On the same line, product categories are always in cursive (*italic*).
                  4. Tags, always in cursive (*italic*)
                  5. Product description.
                  6. Target audience.
                  7. Application area.
                  8. Advantages: Highlight the key benefits that set the product apart from others and explain the added value for users.
                  9. New section with "---".
                  10. Mentora pro hint (can be empty). DO NOT invent, alter, assume, or extend beyond the context. If the context does not contain a hint, explicitly state: "kein Tipp".

                - Always render section names in bold.
                - For the "Mentora Pro Tipp" section, always render "Mentora Pro Tipp 💡:" section name before the content.
                - Always render product details exactly as in this example:
                [Energy-Plus](https://www.ethno-health.com/energy-plus) – *Sport & Vitaliy*
                
                **Schlagworte:** *Sport*
                
                **Produktbeschreibung:** Steigert die Energie im Alltag.
                
                **Zielgruppe:** Late Menschen
                
                **Anwendung:** Dreimal pro Tag
                
                **Vorteile:** Günstig und Effektiv

                ---

                **Mentora Pro Tipp 💡:** Lorem ipsum dolor sit amet esse quia sed id consectetur dolore ab non. Lorem ipsum dolor sit amet ipsum irure ut eius mollit sequi do incididunt quia.
            """,
            description="System prompt for product details.",
        )
        PROMPT_PROPERTY: str = Field(
            default="""
                You MUST take the product name from context.name and the product URL from context.reference_link.
                You MUST render the first line as: [<context.name>](<context.url>) – *<context.categories>*
                You MUST ignore any URLs found in any other fields.
                Never invent or modify the URL or name.

                INSTRUCTIONS:
                - Always use Markdown format.
                - You must always render:
                  1. Product name as Markdown link.
                  2. On the same line, the em dash (–) surrounded by spaces.
                  3. On the same line, product categories are always in cursive (*italic*).
                  4. On the new line, product property.
                  9. New section with "---".
                  5. Mentora pro hint (can be empty). DO NOT invent, alter, assume, or extend beyond the context. If the context does not contain a hint, explicitly state: "kein Tipp".

                - For the "Mentora Pro Tipp" section, always render "**Mentora Pro Tipp 💡:**" section name before the content.
                - Always render "Mentora Pro Tipp 💡:" section header in **bold**.
                - Always render product details exactly as in this example:
                [Energy-Plus](https://www.ethno-health.com/energy-plus) – *Sport & Vitaliy*

                Lorem ipsum dolor sit amet minim ullamco adipisci et laboris et at voluptas sint tempora eaque non.

                ---
                
                **Mentora Pro Tipp 💡:** Lorem ipsum dolor sit amet esse quia sed id consectetur dolore ab non. Lorem ipsum dolor sit amet ipsum irure ut eius mollit sequi do incididunt quia.
            """,
            description="System prompt for product property.",
        )
        PROMPT_QNA: str = Field(
            default="""
            You MUST answer strictly and only based on the provided context.
            - Use ALL relevant information from the context directly related to the user’s question.  
            - DO NOT invent, assume, or extend beyond the context.
            - Always answer in complete, competent, and professional German.  
            - Preserve accuracy and factual correctness exactly as given in the context.  
            - Do not add external knowledge, speculation, or assumptions.  
            - Ensure the answer is concise but fully covers all information present in the context related to the question.
            - At the end render Mentora pro hint (can be empty). DO NOT invent, alter, assume, or extend beyond the context. If the context does not contain a hint, explicitly state: "kein Tipp".

            """,
            description="System prompt for product property.",
        )
        PROMPT_NOTHING_FOUND: str = Field(
            default="""
            INSTRUCTIONS:
            Render only these points:
            - Politely say we've found nothing for your request.
            - Ask to refine the query.
            - Last, you always **must** suggest contacting our customer support. Render all three of our contacts:
              1. Phone: +41 79 894 66 66
              2. WhatsApp: +41 79 894 66 66 or ~Impact Flow
              3. Buche einen Termin  in unserem Kalender.
            - Always render calendar contact as a Markdown link to https://www.eTermin.net/Love369Wins/serviceid/576811?noinitscroll=1.
            - Be concise.

            - **NEVER** invent answer!
            - **NEVER** give ANY recommendations or product links outside the provided context!
            """,
            description="System prompt for product property.",
        )
        TEMPLATE_FOOTER: str = Field(
            default="\n\n---\n\n*Bitte beachte, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!*\n\n",
            description="Footer template (disclaimer).",
        )

        # PostgreSQL connection configuration
        POSTGRES_HOST: str = Field(
            default="r2.peaknetworks.net", description="PostgreSQL host."
        )
        POSTGRES_PORT: int = Field(default=2632, description="PostgreSQL port.")
        POSTGRES_USER: str = Field(
            default="impact_admin", description="PostgreSQL username."
        )
        POSTGRES_PASSWORD: str = Field(
            default="",
            description="PostgreSQL password.",
        )
        POSTGRES_DATABASE: str = Field(
            default="impact_flow", description="PostgreSQL database name."
        )

    def __init__(self):
        self.valves = self.Valves()

        self.query_db = partial(query_db, self)
        self.get_user_name_from_full_name = partial(get_user_name_from_full_name, self)
        self.get_embedding = partial(get_embedding, self)
        self.sanitize_user_input = partial(sanitize_user_input, self)

    context_product = {}

    def get_product_list(self):
        """
        Queries the PostgreSQL database.
        It searches for all available products in the database.
        """
        query = """
                SELECT
                    product_id,
                    info
                FROM (
                         SELECT
                             product_id,
                             jsonb_object_agg(
                                     section,
                                     CASE section
                                         WHEN 'name' THEN regexp_replace(vmetadata->>'name', '^\s*Produktname:\s*', '')
                                         WHEN 'categories' THEN regexp_replace(chunk_text, '^\s*Kategorien:\s*', '')
                                         WHEN 'reference_link' THEN regexp_replace(chunk_text, '^\s*Produk(t?)webseite:\s*', '')
                                         END
                             ) AS info,
                             /* derive a stable sort key from the name */
                             max(regexp_replace(vmetadata->>'name', '^\s*Produktname:\s*', ''))
                             FILTER (WHERE section = 'name') AS sort_name
                         FROM product_chunks
                         WHERE section IN ('name', 'categories', 'reference_link')
                         GROUP BY product_id
                     ) t
                ORDER BY sort_name NULLS LAST \
                """

        results = self.query_db(query, "all")

        return {
            "prompt": self.valves.PROMPT_LIST,
            "data": [{**item["info"]} for item in results],
        }

    def get_category_list(self):
        """
        Queries the PostgreSQL DB for the list of all available categories.
        """
        query = """
                WITH categories AS (
                    SELECT product_id, substring(chunk_text FROM 'Kategorien: (.*)') AS category
                    FROM product_chunks
                    WHERE section = 'categories'
                ),
                     tags AS (
                         SELECT product_id, unnest(string_to_array(substring(chunk_text FROM 'Schlagworte: (.*)'), ', ')) AS tag
                         FROM product_chunks
                         WHERE section = 'tags'
                     )
                SELECT
                    c.category,
                    ARRAY_AGG(DISTINCT t.tag) AS tags
                FROM categories c
                         JOIN tags t ON t.product_id = c.product_id
                GROUP BY c.category
                ORDER BY c.category \
                """
        results = self.query_db(query, "all")
        # print(f"---------> results: {results}")
        # categories = [f"{result['category']}" for result in results]

        data = [
            {"category": {result["category"]}, "tags": {tag for tag in result["tags"]}}
            for result in results
        ]

        # print(f"---------> data: {data}")

        return {
            "prompt": self.valves.PROMPT_CATEGORIES,
            "data": data,
        }

    def get_products_by_category(self, category: str):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """
        if not category:
            return {"prompt": "", "data": "Category is not defined"}

        vector_category = self.get_embedding(category)
        # print(f"---> Category vector: {vector_category}")

        query = """
                SELECT product_id,
                       jsonb_object_agg(
                               section,
                               chunk_text
                       ) AS info
                FROM product_chunks
                WHERE product_id IN (
                    SELECT product_id
                    FROM product_chunks
                    WHERE chunk_text IN (
                        SELECT chunk_text
                        FROM product_chunks
                        WHERE section = 'categories'
                        ORDER BY embedding <#> %s::vector
                        LIMIT 2
                    )
                )
                  AND section IN ('name', 'categories', 'short_description', 'reference_link')
                GROUP BY product_id \
                """

        results = self.query_db(query, "all", (vector_category,))

        if not results or not len(results):
            return None

        return {
            "prompt": (
                self.valves.PROMPT_LIST
                if len(results) > 1
                else self.valves.PROMPT_DETAILS
            ),
            "data": [{**item["info"]} for item in results],
        }

    def get_products_by_property(
            self, property: str, objectives: list[str], user_message=""
    ):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """

        # Change search to tags instead of application area for better results
        if property == "xxx_application_area":
            query = """
                    WITH objectives AS (
                        /* normalize each objective term (passed as text[]) */
                        SELECT ARRAY_AGG(trim(both from normalize_csv(o)::text)) AS oarr
                        FROM unnest(%s::text[]) AS u(o)
                    ),
                         tags AS (
                             /* extract & normalize tags from the 'tags' section rows */
                             SELECT
                                 pc.product_id,
                                 ARRAY_AGG(trim(both from normalize_csv(t)::text)) AS ntags
                             FROM (
                                      SELECT
                                          product_id,
                                          unnest(
                                                  string_to_array(
                                                          regexp_replace(chunk_text, '^\s*Schlagworte:\s*', '', 'i'),
                                                          ','
                                                  )
                                          ) AS t
                                      FROM product_chunks
                                      WHERE section = 'tags'
                                  ) s
                                      JOIN product_chunks pc USING (product_id)
                             GROUP BY pc.product_id
                         ),
                         candidates AS (
                             /* require that the product has a non-empty row for the requested section
                                and at least one tag/objective intersection */
                             SELECT DISTINCT pc.product_id
                             FROM product_chunks pc
                                      JOIN tags tg USING (product_id)
                                      CROSS JOIN objectives o
                             WHERE pc.section = 'tags'
                               AND pc.chunk_text <> ''
                               AND tg.ntags && o.oarr
                         ),
                         scored AS (
                             SELECT
                                 t.product_id,
                                 /* how many objectives are present in tags */
                                 (SELECT COUNT(*) FROM unnest(t.ntags) tt WHERE tt = ANY(o.oarr)) AS match_count
                             FROM tags t
                                      JOIN candidates c ON c.product_id = t.product_id
                                      CROSS JOIN objectives o
                         ),
                         top AS (
                             SELECT product_id
                             FROM scored
                             WHERE match_count > 0
                             ORDER BY match_count DESC
                             -- LIMIT 3
                         )
                    SELECT
                        pc.product_id,
                        jsonb_object_agg(
                                pc.section,
                                CASE section
                                    WHEN 'name' THEN regexp_replace(vmetadata->>'name', '^\\s*Produktname:\\s*', '')
                                    WHEN 'categories' THEN regexp_replace(chunk_text, '^\\s*Kategorien:\\s*', '')
                                    WHEN 'reference_link' THEN regexp_replace(chunk_text, '^\\s*Produk(t?)webseite:\\s*', '')
                                    -- WHEN 'application_area' THEN regexp_replace(chunk_text, '^\\s*Anwendungsbereich:\\s*', '')
                                    WHEN 'tags' THEN regexp_replace(chunk_text, '^\\s*Schlagworte:\\s*', '')
                                    END
                        ) AS info
                    FROM product_chunks pc
                             JOIN top USING (product_id)
                    WHERE pc.section IN ('name', 'tags', 'categories', 'reference_link')
                    GROUP BY pc.product_id
                    ORDER BY (SELECT match_count FROM scored s WHERE s.product_id = pc.product_id) DESC; \
                    """
            params = (objectives,)
        else:
            query = """
                    SELECT
                        product_id,
                        jsonb_object_agg(
                                section,
                                chunk_text
                        ) AS info
                    FROM product_chunks
                    WHERE product_id IN (
                        SELECT product_id
                        FROM product_chunks
                        WHERE section = %s
                          AND chunk_text <> ''
                          AND abs(embedding <#> %s::vector) > 0.5
                        ORDER BY abs(embedding <#> %s::vector) DESC
                        LIMIT 3
                    )
                      AND section IN ('name', 'categories', %s, 'reference_link')
                    GROUP BY product_id \
                    """

            # vector = self.get_embedding(" ".join(objectives))
            vector = self.get_embedding(user_message)
            params = (property, vector, vector, property)

        results = self.query_db(query, "all", params)
        # print(f"----> Results: {results}")

        if isinstance(results, str) or not len(results):
            return None

        return {
            "prompt": (
                self.valves.PROMPT_LIST_BY_PROPERTY
                # if len(results) > 1
                # else self.valves.PROMPT_DETAILS
            ),
            "data": (
                [{"product_info": row["info"]} for row in results]
                # if len(results) > 1
                # else results[0]["info"]
            ),
        }

    def get_product_details(self, product_name):
        """
        Queries the PostgreSQL database using the provided product name.
        For example, it searches for a matching product in the database.
        """
        if not product_name:
            return None

        # print(f"-----> product_name: {product_name}")

        vector = self.get_embedding(product_name)

        query = """
                SELECT
                    jsonb_object_agg(
                            section,
                            CASE section
                                WHEN 'name' THEN regexp_replace(chunk_text, '^\\s*Produktname:\\s*', '', 'i')
                                WHEN 'reference_link' THEN regexp_replace(chunk_text, '^\\s*Produk(t?)webseite:\\s*', '', 'i')
                                ELSE chunk_text
                                END
                    )
                FROM product_chunks
                WHERE product_id IN (
                    SELECT product_id
                    FROM product_chunks, abs(embedding <#> %s::vector) as r
                    WHERE section = 'name'
                      AND r > 0.5
                    ORDER BY r DESC
                    LIMIT 1
                )
                  AND section IN (
                                  'name',
                                  'reference_link',
                                  'categories',
                                  'tags',
                                  'target_audience',
                                  'short_description',
                                  'product_details',
                                  'intake_recommendation',
                                  'application_area',
                                  'ingredients'
                    ) \
                """

        result = self.query_db(query, "val", (vector,))
        # print(f"Result: {result}")

        if not result:
            return None

        # print(f"Produkt details: {result['product_info']}")

        return {
            "prompt": self.valves.PROMPT_DETAILS,
            "data": result,
        }

    Property = Literal[
        "target_audience",
        "intake_recommendation",
        "application_area",
        "ingredients",
        "formulation_origin",
        "user_experience",
    ]

    def get_product_property(self, property: Property, product_name=""):
        """
        Queries the PostgreSQL database for the product property using the provided product property.
        For example, when the user asks about the specific product property
        like target group, application area, user feedback, ingredients, etc.
        """
        name = product_name or self.context_product.get("name", "")

        # print(f"-----> property: {property}")
        # print(f"-----> context product: {self.context_product}")
        # print(f"-----> name: {name}")
        # print(f"-----> product_name: {product_name}")

        if not property or not name:
            return None

        vector_property = self.get_embedding(property)
        vector_name = self.get_embedding(f"Poduktname: {name}")

        query = """
                SELECT jsonb_object_agg(
                               section,
                               CASE section
                                   WHEN 'name' THEN regexp_replace(chunk_text, '^\\s*Produktname:\\s*', '', 'i')
                                   WHEN 'reference_link' THEN regexp_replace(chunk_text, '^\\s*Produk(t?)webseite:\\s*', '', 'i')
                                   ELSE chunk_text
                                   END
                       )
                FROM product_chunks
                WHERE product_id IN (SELECT product_id
                                     FROM product_chunks
                                     WHERE section = 'name'
                                     ORDER BY embedding <#> %s::vector
                                     LIMIT 1)
                  AND section in ('name', 'categories', %s, 'reference_link') \
                """

        result = self.query_db(query, "val", (vector_name, property))
        # print(f"-----> Result: {result}")

        if not result:
            return None

        # Set new context product (not needed)
        # if product_name and self.context_product.get("name", "") != product_name:
        #     self.context_product = {"name": result["name"], "url": result["reference_link"]}

        return {
            "prompt": f"{self.valves.PROMPT_PROPERTY}",
            "data": {**result},
        }

    def get_qna_answer(self, user_message):
        """Queries the PostgreSQL Q&A database for the related disclaimer
        if the user asks questions about pregnancy, medicines, or other stuff, not directly connected to the product properties.
        Examples:
        - Darf das Produkt bei Einnahme von Medikamenten eingenommen werden?
        - Darf ich das Produkt nutzen, wenn ich andere Medikamenten einnehme?
        - Kann ich das produkt während der Schwangerschaft konsumieren?
        - Gibt es Kontraindikationen bei der Einnahme vom Produkt?
        """

        if not user_message:
            return None

        # print(f"--------> User message: {user_message}")
        query_vector = self.get_embedding(user_message)

        query = """
                SELECT answer_text
                FROM q_and_a
                ORDER BY q_embedding <#> %s::vector
                LIMIT 1 \
                """
        result = self.query_db(query, "val", (query_vector,))
        # print(f"-----> Result: {result}")

        if not result:
            return None

        return {
            "prompt": self.valves.PROMPT_QNA,
            "data": {
                "name": self.context_product.get("name", "") or "Ethno Health",
                "reference_link": self.context_product.get("url", "")
                                  or "https://www.ethno-health.com",
                "answer": result,
            },
        }

    ### --- PIPE funciton ---
    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for a related answer,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")
        # print(f"\nBody: {body}\n")

        self.openai = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

        self.embedding = OpenAI(
            base_url=self.valves.EMBEDDING_API_BASE_URL,
            api_key=self.valves.EMBEDDING_API_KEY,
        )

        # Extract the user's first name to use in answers
        username = self.get_user_name_from_full_name(__user__["name"])

        # Extract the product from the last message.
        messages = body.get("messages", [])
        # print(f"\nMessages: {messages}\n")

        if not messages:
            return "No messages provided in the request body."

        for message in messages:
            # print(f"---> Message: {message}")
            if message.get("role", "") == "system":
                system_message = message.get("content", "")
                # print(f"\n-----> System message: {system_message}\n\n")

            elif message.get("role", "") == "assistant":
                assistant_message = message.get("content", "")
                # print(f"\n-----> Assistant message: {assistant_message}\n\n")

                pattern = r"\[([äöüßÄÖÜa-zA-Z0-9\s\-!]+)\]\((https://[^\s)]+)\)"
                name = None
                url = None

                for match in re.finditer(pattern, assistant_message):
                    name = match.group(1)
                    url = match.group(2)
                    # print("Name:", name)
                    # print("URL:", url)

                if name and "/artikeldetail/" in url:
                    self.context_product = {
                        "name": name if name else "",
                        "url": url if url else "",
                    }
                    # print(
                    # f"-----> Context product from history: {self.context_product}"
                    # )

            elif message.get("role", "") == "user":
                user_message = message.get("content", "")
                user_message = (
                    sanitize_user_input(user_message)
                    if user_message
                    else "EMPTY_QUERY_SENTINEL"
                )
                # print(f"-----> User message: {user_message}")

        # Define variables for LLM
        handlers = {
            "get_product_list": self.get_product_list,
            "get_category_list": self.get_category_list,
            "get_products_by_category": self.get_products_by_category,
            "get_products_by_property": self.get_products_by_property,
            "get_product_details": self.get_product_details,
            "get_product_property": self.get_product_property,
            "get_qna_answer": self.get_qna_answer,
        }

        tools_schema = [
            {
                "type": "function",
                "function": {
                    "name": "get_product_list",
                    "description": """
                    Queries the PostgreSQL DB for a list of all available products.

                    Examples:
                    - Welche Produkte habt ihr in Sortiment?
                    - Welche Arten von Produkten habt ihr?
                    
                    """,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_category_list",
                    "description": """
                    Queries the PostgreSQL DB for a list of all available categories.
                    Examples:
                    - Welche Kategorien habt ihr in Sortiment?
                    - Zeige mir alle eure Kategorien an.

                    **DO NOT** use it when user asks about products in the particular category.
                    """,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_products_by_category",
                    "description": """
                    Fetches a list of products in the category.
                    
                    You **must** extract the category name from the user message.
                    You **must** take only one most suitable category name from the category names below:
                    - Beauty & Lifestyle
                    - Body & Clean
                    - Bundles
                    - Chinesische Rezepturen
                    - Ethno Health Coach
                    - Ethno-Events
                    - Ethno-Hausapotheke
                    - Ethno-Rezepturen
                    - Ethno-Rezepturen, Für Kinder geeignet
                    - Ethno-Testsatz
                    - Für Kinder geeignet
                    - Omega Go!
                    - Omega-Öle & Vitalkomplex
                    - Omega-Öle & Vitalkomplex, Für Kinder geeignet
                    - Produktübersicht
                    - Shape Classic, Shape Weight Management
                    - Shape Weight Management
                    - Tibetische Rezeptur Lung
                    - Vitality & Family
                    - Vorzugspaket TCR

                    Examples:
                    – Welche Produkte gibt es in der Kategorie Körper & Reinigung?
                    – Zeig mir die Produkte aus der Kategorie Vitalität & Familie.
                    – Was gibt es in der Kategorie Omega-Öle?

                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category name extracted from user message",
                                "enum": [
                                    "Beauty & Lifestyle",
                                    "Body & Clean",
                                    "Bundles",
                                    "Chinesische Rezepturen",
                                    "Ethno Health Coach",
                                    "Ethno-Events",
                                    "Ethno-Hausapotheke",
                                    "Ethno-Rezepturen",
                                    "Ethno-Rezepturen, Für Kinder geeignet",
                                    "Ethno-Testsatz",
                                    "Für Kinder geeignet",
                                    "Omega Go!",
                                    "Omega-Öle & Vitalkomplex ",
                                    "Omega-Öle & Vitalkomplex, Für Kinder geeignet",
                                    "Produktübersicht",
                                    "Shape Classic, Shape Weight Management",
                                    "Shape Weight Management",
                                    "Tibetische Rezeptur Lung",
                                    "Vitality & Family",
                                    "Vorzugspaket TCR",
                                ],
                            }
                        },
                        "required": ["category"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_products_by_property",
                    "description": """
                    Fetches a list of the most relevant products for the user's request.

                    Use it **ONLY** if the query applies to **many** products.
                    Use it if the 'Ethno Health' string is in the user message.
                    
                    You **must** extract product property from the user message.
                    You **must** take only one most suitable property from this list:
                    - target audience
                    - application area
                    - ingredients
                    - formulation origin
                    - user experience

                    You **must** extract the query **objectives** from the user message. This must be one or 
                    max two words, indicating the user's search subject.
                    You find objectives in the square brackets in these examples:

                    Property "target audience":
                    - Welche Produkte sind am besten für [Sportler] geeignet?

                    Property "ingredients":
                    - Welche Produkte enthalten [Omega-3]?
                    - Gibt es [Proteinpräparate]?
                    - Bei welchen Produkten gibt's [Proteine]?

                    Property "application area":
                    - Welches Produkt hilft bei [Allergien]?
                    - Welche Produkte sind wirksam gegen [Husten]?
                    - Was haben Sie gegen [Husten]?
                    - Haben Sie Produkte für [Klarheit] und [Konzentration]?
                    - Gibt es Produkte für die Unterstützung der [Darmgesundheit]?
                    - Welche Produkte unterstützen beim Lernen?

                    Property "formulation origin":
                    - Welche Produkte wurden in [Tibet] hergestellt?
                    - Wo kommt das Produkt her?
                    - [Woher] kommt die Rezeptur?
                    - Was ist das Besondere an dieser [Rezeptur]?

                    Property "user experience":
                    - [Was sagen die Menschen] über Ethno Health Produkte?
                    - [Was sagen die Leute] über die Produkte?
                    - Gibt es [Erfolgstorys]?

                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property": {
                                "type": "string",
                                "description": "Product property extracted from user message",
                                "enum": [
                                    "target_audience",
                                    "application_area",
                                    "ingredients",
                                    "formulation_origin",
                                    "user_experience",
                                ],
                            },
                            "objectives": {
                                "type": "array",
                                "description": "Query objectives array extracted from user message.",
                            },
                            "user_message": {
                                "type": "srring",
                                "description": "User message",
                            },
                        },
                        "required": ["property", "objectives", "user_message"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_details",
                    "description": """
                    Queries the PostgreSQL database for detailed information about a product.
                    Use when the user refers to a specific product by name, but **there is no specific product property** in the request.

                    You must extract the product name from the user message.
                    You must take the most suitable name from these product names:
                    - Algenkraft
                    - Algenkraft
                    - Alka Box
                    - Astragalus 10
                    - Augenkraft
                    - Ayurveda Balance
                    - Beauty Complex
                    - Blutdruck-Komplex
                    - Blutzucker-Komplex
                    - Bupleurum 9
                    - Burner
                    - COLLAGEN Shots Refill (100 Stück)
                    - Chili choco shake
                    - Cholesterin-Komplex
                    - Cythula 12
                    - Daily 365
                    - Darmkraft
                    - Eiweiss-Vitalkomplex
                    - Enzymkraft
                    - Ethno Health Coach
                    - Ethno-Hausapotheke
                    - Ethno-Testsatz
                    - Forsythiae 10
                    - Frauenkraft
                    - Gehirnkraft
                    - Gelenkkraft
                    - HS-Omega-3 Index-Selbsttest
                    - Herzkraft
                    - Immunkraft
                    - Inflam-Komplex
                    - Lebensfreude
                    - Leberkraft
                    - Lung - inkl. Präsentbox
                    - Lungenkraft
                    - MSM greens
                    - Männerkraft
                    - OPC-Kraft
                    - Omega 3 orange
                    - Omega 3 plus
                    - Omega Duo
                    - Omega Go!
                    - Pilzkraft
                    - Polygoni 7
                    - Rehmannia 6
                    - Schisandra 13
                    - Shape Classic
                    - Vorzugspaket TCR
                    - Weidenkraft
                    - Wurzel-Komplex
                    - Zellschutz-Komplex
                    - Ziziphus 9
                    - alka duo
                    - daily B-complex
                    - daily zenergy
                    - essence aminos
                    - fresh vanilla shake
                    - wild berry shake

                    You find product names in the square brackets in these examples:
                    – Was weisst du über das [Lung] Produkt?
                    – Welche Informationen gibt es über [Brenner]?
                    – Was ist das [Omega Go!] Produkt?
                    - Was ist [Gehirnkraft]?

                    DO NOT use this function if you can't extract the product name.
                    
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "product_name": {
                                "type": "string",
                                "description": "Product name extracted from the context",
                                "enum": product_names,
                            },
                        },
                        "required": ["product_name"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_property",
                    "description": """
                    Fetches the  product property relevant to the user's request.

                    Use it **ONLY** if the query applies to the **single** product.
                    You **must** extract the product property from the user message.
                    You **must** take only the property from this list:
                    - ingredients
                    - application_area
                    - target_audience
                    - user experience
                    - formulation_origin
                    - intake_recommendation

                    **DO NOT** use it if the extracted property is NOT in the list above!
                    **DO NOT** use it if there is "Etho Health" substrin in the user query.
                    
                    Do not use it if the 'Ethno Health' string is in the user message.
                    Extract the product name from the user message if given.

                    User request examples:
                    - Was ist da drin?
                    - Welche Inhaltsstoffe hat das Produkt
                    - Welche Zutaten hat das Produkt
                    - Für was ist das Produkt gut?
                    - Kann das Lung gegen Konzentrastionsstörungen helfen?
                    - Für wen ist das Produkt gedacht?
                    - Was sagen die Leüte über das produkt?
                    - Welche Erfolgsgeschichten gibt's bei daily zenergy?
                    - Wie ist das Produkt entstanden?
                    - Wer hat das Produkt erfunden?
                    - Wie soll ich das Produkt einnehmen?
                    - Wie verwendet man das Lung produkt?

                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property": {
                                "type": "string",
                                "description": "Product property extracted from user message",
                                "enum": [
                                    "target_audience",
                                    "application_area",
                                    "ingredients",
                                    "formulation_origin",
                                    "user_experience",
                                    "intake_recommendation",
                                ],
                            },
                            "product_name": {
                                "type": "string",
                                "description": "Product name extracted from the context",
                                "enum": product_names,
                            },
                        },
                        "required": ["property"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_qna_answer",
                    "description": """
                    Queries the PostgreSQL Q&A database for the related answer to questions **not directly** connected to the product properties.

                    **DO NOT** use it when the user message contains references to the product properties:
                    - ingredients
                    - application_area
                    - target_audience
                    - user experience
                    - formulation_origin
                    - intake_recommendation

                    Use it when the user asks about:
                    - Etho Health
                    - Mentora
                    - Einnahme von Medikamenten
                    - Schwangerschaft
                    - Stillzeit
                    - Kontraindikationen
                    - Nebenwirkungen
                    - Krebs Diagnose
                    - Gesundheit
                    - Produktqualität
                    - Qualitätsmerkmale
                    - Produktkombinationen
                    - Kombination
                    - Produktverträglichkeit
                    - Produktvergleich
                    - Produktunterschiede
                    - Produktlagerung
                    - Produktwirksamkeit
                    - Tägliche Anwendung von Produkten
                    - Mentor, Berater, Coach          

                    Examples:
                    - Darf das Produkt bei Einnahme von Medikamenten eingenommen werden?
                    - Darf ich das Produkt nutzen, wenn ich andere Medikamenten einnehme?
                    - Kann ich das produkt während der Schwangerschaft konsumieren?
                    - Gibt es Kontraindikationen bei der Einnahme vom Produkt?
                    - Wie wirken sich essence aminos auf die Haut während der Schwangerschaft aus?
                    - Kann ich das Produkt während der Schwangerschaft einnehmen?
                    - Können schwangere Frauen Ethno Health-Produkte verwenden?
                    - Kann das Produkt während der Einnahme von Medikamenten eingenommen werden?
                    - Darf ich das Produkt verwenden, wenn ich andere Medikamente einnehme?
                    - Ist das Produkt vegan und welche Qualitätsmerkmale werden genannt?
                    - Was macht die hochwertigen, natürlichen Inhaltsstoffe von Ethno Health so besonders wirksam für das tägliche Wohlbefinden?
                    - Inwiefern profitieren Vegetarier und Veganer von der umfassenden Produktpalette, die Ethno Health anbietet?
                    - Mit welchen Routinen lässt sich Lung gut kombinieren?
                    - Welche Produkte lassen sich gut mit Lung kombinieren?
                    - Was ist Mentora?
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_message": {
                                "type": "string",
                                "description": "User message",
                            }
                        },
                        "required": ["user_message"],
                    },
                },
            },
        ]

        # print(f"--> tools_schema:\n{tools_schema}")
        system_prompt_tools = (
                """
        You are a product assistant.
        Respond *only* with valid JSON, no explanations.
        
        You have access to the following tools:
        
        """
                + json.dumps(tools_schema)
                + """

USE *EXACTLY* THIS SCHEMA:
{
  "name": string,
  "arguments": object
}

**ALWAYS use key "name"** — never "response_function" or variants.
**ALWAYS use key "arguments"** — never "parameters" or variants.

Here are acceptable examples:

{"name":"get_product_list","arguments":{}}
{"name":"get_products_by_property", "arguments":{"property": "target_audience", "objectives": ["Sportler"], "user_message": "Für wen ist das Produkt gut?"}
{"name":"get_product_details","arguments":{"product_name":"Lung"}}
{"name":"get_product_property","arguments":{"property": "ingredients"}}
{"name":"get_product_property","arguments":{"property": "target_audience", "product_name": "Burner"}}
{"name":"get_disclaimer","arguments":{}}

Begin your response now in this JSON-only format.
        """
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt_tools,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

        openai = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

        start_time = time.perf_counter()

        response = self.openai.chat.completions.create(
            model=self.valves.TOOLS_MODEL_ID,
            messages=messages,
            stream=False,
            temperature=0,
        )

        # print(f"-----> response: {response}")

        end_time = time.perf_counter()
        duration = end_time - start_time

        print("================================================")
        print("------------ Tool search query -----------------")
        print(f"- User: {__user__['name']}")
        print(f"- Model: {response.model}")
        print("------------------------------------------------")

        ### Statistic
        if hasattr(response, "total_duration"):
            # print(f"- Load duration: {(response.load_duration / 1e9):.1f}s")
            # print(f"- Eval count: {response.eval_count}")
            # print(f"- Eval duration: {(response.eval_duration / 1e9):.1f}s")
            print(f"- Prompt eval count: {response.prompt_eval_count}")
            print(
                f"- Prompt eval duration: {(response.prompt_eval_duration / 1e9):.1f}s"
            )
            print(f"- Total duration: {(response.total_duration / 1e9):.1f}s")
        elif hasattr(response, "usage"):
            print(f"- Prompt tokens: {response.usage.prompt_tokens}")
            print(f"- Total tokens: {response.usage.total_tokens}")

        # print(f"Function search response: {response}")

        function_name = ""
        arguments = {}
        result = {}

        # Catch Ollama and OpenAI response format diffs
        if hasattr(response, "choices"):
            message = response.choices[0].message
        else:
            message = response["message"]

        if hasattr(message, "tool_calls") and message.tool_calls:
            print("--------------- Tool call ----------------------")
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments)
        else:
            content = json.loads(message.content)
            print("--------------- No tool call -------------------")

            if not content:
                return "No handler defined for this tool call."

            # LLMs give different responses by tool search
            if "name" in content:
                function_name = content["name"]
                arguments = content["arguments"]
            elif "items" in content:
                for key, value in content.items():
                    if (
                            isinstance(value, dict)
                            and "name" in value
                            and "arguments" in value
                    ):
                        function_name = value["name"]
                        arguments = value["arguments"]
                        break

        db_query_start = time.perf_counter()

        try:
            if (
                    hasattr(arguments, "product_name")
                    and arguments["product_name"] == "Ethno Health"
            ):
                result = handlers["get_general_info"](user_message)
            else:
                if function_name in handlers:
                    result = handlers[function_name](**arguments)

        except NameError as e:
            result = {"prompt": "", "data": e}

        end_time = time.perf_counter()

        print(f"- Context product: {self.context_product}")
        print(f"- Function name: {function_name}")
        print(f"- Arguments: {arguments}")
        print(f"- User message: {user_message}")
        print("================================================")
        print(f"Tool search time: {duration:.1f} s")
        print(f"DB query duration: {end_time - db_query_start:.1f} s")
        print(f"Total tool time: {end_time - start_time:.1f} s")
        print("================================================")

        if result:
            prompt = {result.get("prompt", "")}
            context = f"Context: \n\n{result.get('data', '')}\n\n"

            print(f"Function call result: {result.get('data', '')}")
            print("================================================")
        else:
            prompt = self.valves.PROMPT_NOTHING_FOUND
            context = ""

        messages = [
            {
                "role": "system",
                "content": f"""                
                Username: {username}                
                
                {system_message}
                
                {prompt}
                """,
            },
            {
                "role": "user",
                "content": f"{context}\n{user_message}",
            },
        ]

        # print(f"\nMessages: {messages}\n")

        try:
            start_time = time.perf_counter()
            first_chunk = True

            print("================================================")
            print(f"- Model: {self.valves.RAG_MODEL_ID}")
            print("------------------------------------------------")

            for chunk in self.openai.chat.completions.create(
                    model=self.valves.RAG_MODEL_ID,
                    messages=messages,
                    stream=True,
                    max_tokens=16384,
                    temperature=body.get("temperature", 0),
                    top_p=body.get("top_p", 0.3),
                    extra_body={"top_k": 5},
            ):
                # print(f"---> chunk: {chunk}")
                if first_chunk:
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    print("------------------------------------------------")
                    print(f"- Time to first token: {duration:.1f} seconds")
                    print("------------------------------------------------")
                    first_chunk = False

                choice = chunk.choices[0]

                if choice.finish_reason == "stop":
                    if chunk.usage:
                        print(f"- Prompt tokens: {chunk.usage.prompt_tokens}")
                        print(f"- Completion tokens: {chunk.usage.completion_tokens}")
                        print(f"- Total tokens: {chunk.usage.total_tokens}")

                response = choice.delta.content or ""
                # print(f"Response: {response}")
                yield response

            yield self.valves.TEMPLATE_FOOTER

            end_time = time.perf_counter()
            duration = end_time - start_time
            print("------------------------------------------------")
            print(f"Chat completion processing time: {duration:.1f} seconds")
            print("================================================")

        except Exception as e:
            yield f"Error: {e}"
