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
    parse_template,
)
from open_webui.retrieval.functions.data import (
    product_names,
    product_properties,
    categories,
)


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

Always render the product name and category in a separate section

INSTRUCTIONS:
- You must  always render for each product:
1. Horizontal line (---).
2. Product name as the Markdown link.
3. On the same line, the em dash (–) surrounded by spaces.
4. On the same line, categories in cursive (*italic*).
5. The product property section or short description.

- Take the product name from the JSON "name" property and the product link from the "reference_link" property.
- Never invent, alter, or change the product names. Render it exactly as taken from the context.

- Render **every product exactly** like in this example:            
[Lorem Ipsum](https://www.ethno-health.com/artikeldetail/lorem-ipsum) – *Lorem & Ipsum*

Lorem ipsum dolor sit amet tempor dolor qui reprehenderit qui consequuntur voluptas sit voluptate culpa eos nisi. Lorem ipsum dolor sit amet cillum magnam magnam aliquip aut quasi sed sequi lorem. 

IMPORTANT: You must always render the last section with the product property section or short description.

            """,
            description="System prompt for product list.",
        )
        PROMPT_CATEGORIES: str = Field(
            default="""

Task:
You must render all categories from the list.
For each category, you must render the category name and the list of the category products as Markdown links.

Instructions:
- Always use Markdown format.
- For each category from the context, you must always render: category in **bold**, em dash ( – ), the list of category products as Markdown links.
- Take the category name from the "category" and the product list from the "products"  properties of the context JSON.
- Never change, invent, or alter category, product names, or links. Render them EXACTLY as given.
- You must render every category exactly as in this example:
**category name 1** – [name 1](link 1)

IMPORTANT: You must always render every category product as the Markdown link.
            """,
            description="System prompt for product list.",
        )
        PROMPT_DETAILS: str = Field(
            default="""

Render the product name as a Markdown link, categories, your answer, and the Mentora pro hint.
NEVER change or alter product name ({{NAME}}) and url ({{REFERENCE_LINK}}). ALWAYS render it exactly as given.
You must use Markdown format.
IMPORTANT: You must always render the product name and categories in the first line as a SEPARATE section, you answer follows in the next section.

INSTRUCTIONS:
- Always use Markdown format.
- You must always create the following sections using the JSON object from the context:
  1. Product name and categories section exactly like this: "[{{NAME}}]({{REFERENCE_LINK}}) – *{{CATEGORIES}}*"
  2. Combinable with the products section as Markdown links.
  3. Product description section: "{{SHORT_DESCRIPTION}}".
  4. Target audience section based {{TARGET_AUDIENCE}}.
  5. Application area section: {{APPLICATION_AREA}}.
  6. Advantages section: highlight the key benefits based on the context information.
  7. New section with "---".
  8. Mentora pro hint exactly like this: "**Mentora Pro Tipp** 💡: {{MENTORA_PRO_HINT}}".

- Always render section names in bold.
- For the "Combinable with products" section:
  1. You must always find the link in the "{{COMBINABLE_LINKS}}" by name
  2. You must always render each product name as the Markdown link.
- For the "Advantages" section, you must always highlight the key benefits that set the product apart from others and explain the added value for users.
- Always render product details exactly as in this example:
[{{NAME}}]({{REFERENCE_LINK}}) – *{{CATEGORIES}}*

**Gut kmombinierbar mit:** {{COMBINABLE_LINKS}}

**Produktbeschreibung:** {{SHORT_DESCRIPTION}}

**Zielgruppe:**
{{TARGET_AUDIENCE}}

**Anwendung:**
{{APPLICATION_AREA}}

**Vorteile:**
Lorem ipsum dolor sit amet adipisci dolor et mollit voluptatem. Lorem ipsum dolor sit amet beatae fugit esse. Lorem ipsum dolor sit amet ut sed neque totam amet qui esse. 

---

**Mentora Pro Tipp** 💡: {{MENTORA_PRO_HINT}}


IMPORTANT: you MUST ALWAYS render every product name in the "Combinable with products" section as the Markdown link!

            """,
            description="System prompt for product details.",
        )
        PROMPT_PROPERTY: str = Field(
            default="""

Render the product name as a Markdown link, categories, your answer, and the Mentora pro hint.
NEVER change or alter product name ({{NAME}}) and url ({{REFERENCE_LINK}}). ALWAYS render it exactly as given.
You must use Markdown format.
IMPORTANT: You must always render the product name and categories in the first line as a SEPARATE section, you answer follows in the next section.

Instructions:
You must always create the following sections:
  1. The first section with text: "[{{NAME}}]({{REFERENCE_LINK}}) – *{{CATEGORIES}}*"
  2. The second section with your answer.
  3. The third section with "---".
  4. The fourth section with the text: "**Mentora Pro Tipp** 💡: {{MENTORA_PRO_HINT}}".
  
  You must always render the output exactly as in this example:
  [{{NAME}}]({{REFERENCE_LINK}}) – *{{CATEGORIES}}*
  
  Lorem ipsum dolor sit amet adipisci dolor et mollit voluptatem. Lorem ipsum dolor sit amet beatae fugit esse. Lorem ipsum dolor sit amet ut sed neque totam amet qui esse.
   
  ---
  
  **Mentora Pro Tipp** 💡: {{MENTORA_PRO_HINT}}
  
  
IMPORTANT: You MUST ALWAYS render the product name and categories in a separate section!
      
            """,
            description="System prompt for product property.",
        )
        PROMPT_QNA: str = Field(
            default="""

Task:
You MUST answer strictly and only based on the provided context.

Instructions:
- Never strip, change, or alter the Markdown links from the context; you must render them as is.
- Use ALL relevant information from the context directly related to the user’s question.  
- DO NOT invent, assume, or extend beyond the context.
- Always answer in complete, competent, and professional German.  
- Preserve accuracy and factual correctness exactly as given in the context.  
- Do not add external knowledge, speculation, or assumptions.  
- Ensure the answer is concise but fully covers all information present in the context related to the question.

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
                                     chunk_text
                             ) AS info,
                             /* derive a stable sort key from the name */
                             max(vmetadata->>'name')
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
                    SELECT
                        product_id,
                        chunk_text AS category
                    FROM product_chunks
                    WHERE section = 'categories'
                ),
                     product_info AS (
                         SELECT
                             product_id,
                             vmetadata->>'name' AS name,
                             vmetadata->>'reference_link' AS reference_link
                         FROM product_chunks
                         WHERE section = 'name' OR section = 'reference_link'
                     ),
                     aggregated_products AS (
                         SELECT
                             product_id,
                             MAX(name) AS name,
                             MAX(reference_link) AS reference_link
                         FROM product_info
                         GROUP BY product_id
                     )
                SELECT
                    c.category AS category,
                    jsonb_agg(
                            jsonb_build_object(
                                    'name', ap.name,
                                    'link', ap.reference_link
                            )
                    ) AS products
                FROM categories c
                         JOIN aggregated_products ap ON ap.product_id = c.product_id
                WHERE c.category IS NOT NULL
                  AND ap.name IS NOT NULL
                  AND ap.reference_link IS NOT NULL
                GROUP BY c.category
                ORDER BY c.category; \
                """
        results = self.query_db(query, "all")
        # print(f"---------> results: {results}")
        return {
            "prompt": self.valves.PROMPT_CATEGORIES,
            "data": results,
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
            "prompt": self.valves.PROMPT_LIST_BY_PROPERTY,
            "data": [{**item["info"]} for item in results],
        }

    def get_products_by_property(
            self, property: str, objectives: list[str], user_message=""
    ):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """

        # print(f"---> get_products_by_property")
        # print(f"---> property: {property}")
        # print(f"---> objectives: {objectives}")
        # print(f"---> user_message: {user_message}")

        # Change search to tags instead of application area for better results
        # if property == "application_area":

        query = """
            SET hnsw.ef_search = 40;
            SELECT set_limit(0.20); 
            
            WITH
            q AS (
              SELECT
                normalize_csv(%s) AS qtags,
                COALESCE(websearch_to_tsquery('german', NULLIF(%s,'')), to_tsquery('german','')) AS qtext,
                %s::vector AS qvec,
                %s as prop
            ),
            
            -- 1) exact tag match: any overlap between query tags and stored tags
            exact_tag AS (
              SELECT DISTINCT p.product_id, 1.0 AS score
              FROM product_chunks p, q
              WHERE p.section = 'tags'
                AND p.tags_arr && q.qtags
            ),
            
            has_exact AS (
              SELECT EXISTS(SELECT 1 FROM exact_tag) AS found
            ),
            
            -- 2) scores per product (tags trigram + property dense & bm25)
            scored AS (
              SELECT
                pid AS product_id,
            
                /* robust fuzzy tag score: plural/singular + typos */
                (SELECT MAX(GREATEST(
                          word_similarity(t, qt),                                    -- word-aware
                          similarity(t, qt),                                         -- trigram
                          1 - (levenshtein(t, qt)::float / GREATEST(length(t), length(qt)))  -- edit distance
                       ))
                 FROM unnest(any_value.tags_arr) AS t
                 CROSS JOIN LATERAL unnest((SELECT qtags FROM q)) AS qt
                ) AS s_tags,
            
                /* best property dense sim (cosine) */
                (SELECT MAX(1 - (pa.embedding <=> (SELECT qvec FROM q)))
                 FROM product_chunks pa, q
                 WHERE pa.product_id = pid
                   AND pa.section = (SELECT prop FROM q)  -- Fixed: use subquery instead of q.prop
                   AND (SELECT qvec FROM q) IS NOT NULL
                ) AS s_app_dense,
            
                /* best property BM25 */
                (SELECT MAX(ts_rank_cd(pa2.app_tsv, (SELECT qtext FROM q)))
                 FROM product_chunks pa2, q
                 WHERE pa2.product_id = pid
                   AND pa2.section = (SELECT prop FROM q)  -- Fixed: use subquery instead of q.prop
                ) AS s_app_bm25
            
              FROM (
                SELECT DISTINCT product_id AS pid,
                       MAX(tags_arr) OVER (PARTITION BY product_id) AS tags_arr
                FROM product_chunks pc, q
                WHERE pc.section IN ('tags', (SELECT prop FROM q))  -- Fixed: use subquery
              ) any_value
            ),
            
            -- NORMALIZE EACH CHANNEL TO [0,1]
            norm AS (
              SELECT
                product_id,
                COALESCE((s_tags - MIN(s_tags) OVER())
                         / NULLIF(MAX(s_tags) OVER() - MIN(s_tags) OVER(), 0), 0) AS n_tags,
                COALESCE((s_app_dense - MIN(s_app_dense) OVER())
                         / NULLIF(MAX(s_app_dense) OVER() - MIN(s_app_dense) OVER(), 0), NULL) AS n_app_dense,
                COALESCE((s_app_bm25 - MIN(s_app_bm25) OVER())
                         / NULLIF(MAX(s_app_bm25) OVER() - MIN(s_app_bm25) OVER(), 0), NULL) AS n_app_bm25
              FROM scored
            ),
            
            -- DYNAMIC WEIGHT RENORMALIZATION (only non-NULL channels count)
            hybrid AS (
              SELECT
                product_id,
                (
                  COALESCE(0.60 * n_tags, 0) +
                  COALESCE(0.25 * n_app_dense, 0) +
                  COALESCE(0.15 * n_app_bm25, 0)
                ) / NULLIF(
                  (CASE WHEN n_tags      IS NOT NULL THEN 0.60 ELSE 0 END) +
                  (CASE WHEN n_app_dense IS NOT NULL THEN 0.25 ELSE 0 END) +
                  (CASE WHEN n_app_bm25  IS NOT NULL THEN 0.15 ELSE 0 END),
                  0
                ) AS score
              FROM norm
            ),
            
            -- FINAL SELECTION: exact matches first; otherwise, take top-K by hybrid (no hard 0.9 gate)
            final_ids AS (
              SELECT product_id, score FROM exact_tag
              UNION ALL
              SELECT h.product_id, h.score
              FROM hybrid h, has_exact hx
              WHERE NOT hx.found
              -- AND score >= 0.8
              ORDER BY score DESC
              LIMIT 3
            ),
            
            -- Get the property name for the final SELECT
            prop_name AS (
              SELECT prop FROM q LIMIT 1
            )
            
            SELECT jsonb_build_object(
                'product_id', f.product_id,
                'score', f.score,
                'name', MAX(pc.chunk_text) FILTER (WHERE pc.section = 'name'),
                'categories', MAX(pc.chunk_text) FILTER (WHERE pc.section = 'categories'),
                pn.prop, MAX(pc.chunk_text) FILTER (WHERE pc.section = pn.prop),  -- Fixed: use prop_name CTE
                'reference_link', MAX(pc.chunk_text) FILTER (WHERE pc.section = 'reference_link')
            ) AS info
            FROM final_ids f
            CROSS JOIN prop_name pn
            JOIN product_chunks pc
              ON pc.product_id = f.product_id
             AND pc.section IN ('name','tags','categories',pn.prop,'reference_link')  -- Fixed: use pn.prop
            GROUP BY f.product_id, f.score, pn.prop
            ORDER BY f.score DESC
            LIMIT 3;
        """
        vec_query = self.get_embedding(user_message) if user_message else None
        params = (",".join(objectives), user_message, vec_query, property)
        results = self.query_db(query, "all", params)
        # print(f"----> Results: {results}")

        if isinstance(results, str) or not len(results):
            return None

        return {
            "prompt": self.valves.PROMPT_LIST_BY_PROPERTY,
            "data": [{"product_info": row["info"]} for row in results],
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
                            chunk_text
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
                                  'combinable_with',
                                  'target_audience',
                                  'short_description',
                                  'product_details',
                                  'intake_recommendation',
                                  'application_area',
                                  'ingredients',
                                  'hint'
                    ) \
                """

        result = self.query_db(query, "val", (vector,))
        # print(f"Result: {result}")

        if not result:
            return None

        sql = """
              SELECT jsonb_object_agg(
                             pc.vmetadata->>'name',
                             pc.chunk_text
                     ) AS links
              FROM product_chunks pc
              WHERE pc.section = 'reference_link'
                AND EXISTS (
                  SELECT 1
                  FROM unnest(normalize_csv(%s)) AS pat
                  WHERE lower(pc.vmetadata->>'name') ILIKE pat || '%%'
              ) \
              """
        res = self.query_db(sql, "one", (f"{result['combinable_with']}",))
        links = res["links"] if res else None

        # print(f"Combinable links: {links}")

        cols = [
            "name",
            "reference_link",
            "categories",
            "combinable_with",
            "target_audience",
            "short_description",
            "product_details",
            "intake_recommendation",
            "application_area",
            "ingredients",
            "hint",
        ]
        return {
            "prompt": parse_template(self.valves.PROMPT_DETAILS, cols, result),
            "data": {**result, "combinable_links": links},
        }

    Property = Literal[*product_properties]

    def get_product_property(self, property: Property, product_name=""):
        """
        Queries the PostgreSQL database for the product property using the provided product property.
        For example, when the user asks about the specific product property
        like target group, application area, user feedback, ingredients, etc.
        """
        name = product_name or self.context_product.get("name", "")

        # print(f"-----> property: {property}")
        # print(f"-----> product_name: {product_name}")
        # print(f"-----> context product: {self.context_product}")
        # print(f"---> Use product name: {name}")

        if not property or not name:
            return None

        vector_name = self.get_embedding(name)

        query = """
                SELECT jsonb_object_agg(
                               section,
                               chunk_text
                       )
                FROM product_chunks
                WHERE product_id IN (
                    SELECT product_id
                    FROM product_chunks
                    WHERE section = 'name'
                    ORDER BY embedding <#> %s::vector
                    LIMIT 1)
                  AND section in ('name', 'reference_link', 'categories', %s, 'hint') \
                """

        result = self.query_db(query, "val", (vector_name, property))
        # print(f"---> result: {result}")

        if not result:
            return None

        # Set new context product (not needed)
        # if product_name and self.context_product.get("name", "") != product_name:
        #     self.context_product = {"name": result["name"], "url": result["reference_link"]}

        cols = ["name", "reference_link", "categories", property, "hint"]
        return {
            "prompt": parse_template(self.valves.PROMPT_PROPERTY, cols, result),
            "data": result,
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
                "name": self.context_product.get("name", ""),
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

                pattern = r"^\[([äöüßÄÖÜa-zA-Z0-9\s\-\.!]+)\]\((https://[^\s)]+)\)"
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
                    Use ONLY if the user clearly refers to multiple products and no parameters are defined in the user query.

                    Examples:
                    - Welche Produkte habt ihr in Sortiment?
                    - Welche Arten von Produkten habt ihr?
                    - Welche Produkte gibt es?
                    
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
                    "description": f"""
                    Fetches a list of products in the category.
                    Default for the category parameter.
                    Use ONLY if the user clearly refers to multiple products.
                    
                    You must extract the category name from the user message.
                    You must take only one most suitable category name from this list: {', '.join(categories)}

                    Examples:
                    – Welche Produkte gibt es in der Kategorie Körper & Reinigung?
                    – Zeig mir die Produkte aus der Kategorie Vitalität & Familie.
                    – Was gibt es in der Kategorie Omega-Öle?
                    - Zeig mir Produkte von Body & Clean.

                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category name extracted from user message",
                                "enum": categories,
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
                    "description": f"""
                    Fetches a list of the most relevant products for the user's request.
                    
                    DO NOT USE if the user clearly refers to one specific product (cues: “das Produkt”, “dieses Produkt”, a product name, or anaphora to a previously named single product).
                    DO NOT USE if the message names a specific product from this list {', '.join(product_names)}, and asks about combinations. Route to get_product_property with property="combinable_with".

                    USE BY DEFAULT for symptom/benefit queries without an explicit single product reference.
                    Use ONLY if the user clearly refers to multiple products.
                    
                    You **must** extract product property from the user message.
                    You **must** take only one most suitable property from this list: "target_audience", "application_area", "ingredients", "formulation_origin", "user_experience"

                    You **must** extract the query **objectives** from the user message. This must be one or max two words, indicating the user's search subject.
                    
                    Examples:
                    - Welche Produkte sind am besten für Sportler geeignet? --> target_audience
                    - Welche Produkte enthalten Omega-3? --> ingredients
                    - Gibt es Proteinpräparate? --> ingredients
                    - Bei welchen Produkten gibt's Proteine? --> ingredients
                    - Welche Produkte helfen bei Allergien? --> application_area
                    - Welche Produkte sind wirksam gegen Husten? --> application_area
                    - Was hilft gegen Stress? --> application_area
                    - Was kann mir bei der Konzentration helfen? --> application_area
                    - Was unterstüzt mein Fokus? --> application_area
                    - Was haben Sie gegen Arthrose? --> application_area
                    - Haben Sie Produkte für Klarheit und Konzentration? --> application_area
                    - Gibt es Produkte für die Unterstützung der Darmgesundheit? --> application_area
                    - Welche Produkte unterstützen beim Lernen? --> application_area
                    - Welche Produkte wurden in Tibet hergestellt? --> formulation_origin
                    - Wo kommt das Produkt her? --> formulation_origin
                    - Woher kommt die Rezeptur? --> formulation_origin
                    - Was ist das Besondere an dieser Rezeptur? --> formulation_origin
                    - Was sagen die Menschen über Ethno Health Produkte? --> user experience
                    - Was sagen die Leute über die Produkte? --> user experience
                    - Gibt es Erfolgstorys? --> user experience

                    Wenn der Nutzer kein konkretes Produkt nennt und kein Singular-Hinweis (“das/dieses Produkt”) vorhanden ist, verwende standardmäßig dieses Tool.
                    Pass ONLY: property (required) and product_name (optional). Keine anderen Felder.
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property": {
                                "type": "string",
                                "description": "Product property extracted from user message",
                                "enum": product_properties,
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
                    "description": f"""
                    Queries the PostgreSQL database for detailed information about a product.
                    Use when the user refers to a specific product by name, but **there is no specific product property** in the request.

                    You must extract the product name from the user message.
                    You must take the most suitable name from this list: {', '.join(product_names)}

                    Examples:
                    – Was weisst du über das Lung Produkt?
                    – Welche Informationen gibt es über Brenner?
                    – Was ist das Omega Go! Produkt?
                    - Was ist Gehirnkraft?

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
                    "description": f"""
                    Fetches the  product property relevant to the user's request.

                    USE ONLY when the user refers to one specific product (explicit name or singular cues: “das Produkt”, “dieses Produkt”, “dieses Präparat”, or anaphora to a previously mentioned single product).
	                DO NOT USE for generic symptom/benefit questions without a specific product.

                    Pass ONLY these parameters: property (required) and product_name (optional).
                    DO NOT include objectives, user_message, or any other fields. Extra fields will be ignored.

                    You **must** extract the product property from the user message.
                    You **must** take only the property from this list: {', '.join(product_properties)}

                    PROPERTY LEXICON (German → property key):
                    - “Rezeptur”, “entstanden”, “entstehung”, “erfunden”, “entwickelt”, “Ursprung”, “Herkunft”, “woher”, “tradition”, “Formulierung”, “Konzept”, “nach … Medizin/Tradition (Ayurveda, TCM, Tibet)” → formulation origin.
                    - Wenn diese Wörter vorkommen (auch ohne Produktname), ist die gesuchte Produkteigenschaft formulation origin.

                    product_name is optional. If the user did not name a product but uses anaphora (e.g., ‘das Produkt’, ‘dieses Produkt’), call this function without product_name.
                    Call this function without the product name parameter, if the product name does not explicitly exist in the user query.

                    Examples:
                    - Für was ist das Produkt gut? → {{"property":"application_area"}}
                    - Was ist da drin? → {{"property":"inhaltsstoffe"}}
                    - Welche Inhaltsstoffe hat das Produkt → {{"property":"inhaltsstoffe"}}
                    - Welche Zutaten hat das Produkt → {{"property":"inhaltsstoffe"}}
                    - Sind die Inhaltsstoffe rein pflanzlich? → {{"property":"inhaltsstoffe"}}
                    - Kann das Produkt gegen Konzentrastionsstörungen helfen? → {{"property":"application_area"}}
                    - Kann das Produkt gegen Allergien eingesetzt werden? → {{"property":"application_area"}}
                    - Kann ich das Produkt gegen Allergien verwenden? → {{"property":"application_area"}}
                    - Für wen ist das Produkt gedacht? → {{"property":"target_audience"}}
                    - Für wen ist das gut? → {{"property":"target_audience"}}
                    - Wie fühlen sich die Menschen nach der Einnahme? → {{"property":"user_experience"}}
                    - Was sagen die Leüte über das produkt? → {{"property":"user_experience"}}
                    - Welche Erfolgsgeschichten gibt's bei daily zenergy? → {{"property":"user_experience"}}
                    - Wie ist das Produkt entstanden? → {{"property":"formulation origin"}}
                    - Wer hat das Produkt erfunden? → {{"property":"formulation origin"}}
                    - Wer hat die Rezeptur von Gelenkkraft entwickelt? → {{"property":"formulation origin","product_name":"Gelenkkraft"}}
                    - Wie soll ich das Produkt einnehmen? → {{"property":"intake_recommendation"}}
                    - Wie verwendet man das Produkt produkt? → {{"property":"intake_recommendation"}}
                    - Wie ist die Rezeptur entstanden? → {{"property":"formulation_origin"}}
                    - Mit welchen Produkten kann ich das kombinieren? → {{"property":"combinable_with"}}
                    - Welche Produkte sind gut mit dem Produkt kombinierbar? → {{"property":"combinable_with"}}

                    Wenn kein Produktname oder Singular-Hinweis vorhanden ist, verwende dieses Tool nicht.
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "property": {
                                "type": "string",
                                "description": "Product property extracted from user message",
                                "enum": product_properties,
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
                    "description": f"""
                    Queries the PostgreSQL Q&A database for the related answer to questions **not directly** connected to the product properties.
                    Default for general, NOT product-related questions.
                     
                    DO NOT USE if the message contains any keyword that maps to a product property (see examples): {', '.join(product_properties)}
                    Formulation origin cue words (German): “Rezeptur”, “entstanden/Entstehung”, “erfunden”, “entwickelt”, “Ursprung”, “Herkunft”, “Formulierung”, “Tradition (Ayurveda/TCM/Tibet)”.
                    Wenn solche Wörter vorkommen, wähle nicht dieses Tool.

                    DO NOT use it when the user clearly refers to the product:
                    - names from this list: {', '.join(product_names)}
                    - categories from this list: {', '.join(categories)}

                    You **must** extract the query **objectives** from the user message. This must be one or max two words, indicating the user's search subject.
                    **DO NOT** use it if the extracted query **objectives** are clearly not in this list:
                    - Etho Health
                    - Etho Health Produkte
                    - Mentora
                    - Einnahme von Medikamenten
                    - Schwangerschaft, Schwangere
                    - Stillzeit
                    - Kontraindikationen
                    - Nebenwirkungen
                    - Krebs Diagnose
                    - Gesundheit
                    - Produktqualität
                    - Qualitätsmerkmale
                    - Produktkombinationen
                    - Produktverträglichkeit
                    - Produktvergleich
                    - Produktunterschiede
                    - Produktlagerung
                    - Produkformen
                    - Produktwirksamkeit
                    - Pflanzengruppen
                    - Tägliche Anwendung von Produkten
                    - Vegetarier
                    - Veganer

                    Examples:
                    - Darf das Produkt bei Einnahme von Medikamenten eingenommen werden?
                    - Darf ich das Produkt nutzen, wenn ich andere Medikamenten einnehme?
                    - Gibt es Kontraindikationen bei der Einnahme vom Produkt?
                    - Können schwangere Frauen Ethno Health-Produkte verwenden?
                    - Können Schwangere dieses Produkt einnehmen?
                    - Kann das Produkt während der Einnahme von Medikamenten eingenommen werden?
                    - Darf ich das Produkt verwenden, wenn ich andere Medikamente einnehme?
                    - Ist das Produkt vegan und welche Qualitätsmerkmale werden genannt?
                    - Was macht die hochwertigen, natürlichen Inhaltsstoffe von Ethno Health so besonders wirksam für das tägliche Wohlbefinden?
                    - Inwiefern profitieren Vegetarier und Veganer von der umfassenden Produktpalette, die Ethno Health anbietet?
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "user_message": {"type": "string"},
                            "objectives": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": [
                                        "Ethno Health",
                                        "Ethno Health Produkte",
                                        "Mentora",
                                        "Einnahme von Medikamenten",
                                        "Schwangerschaft",
                                        "Stillzeit",
                                        "Kontraindikationen",
                                        "Nebenwirkungen",
                                        "Krebs Diagnose",
                                        "Gesundheit",
                                        "Produktqualität",
                                        "Qualitätsmerkmale",
                                        "Produktkombinationen",
                                        "Produktverträglichkeit",
                                        "Produktvergleich",
                                        "Produktunterschiede",
                                        "Produktlagerung",
                                        "Produktformen",
                                        "Produktwirksamkeit",
                                        "Pflanzengruppen",
                                        "Tägliche Anwendung von Produkten",
                                        "Vegetarier",
                                        "Veganer",
                                    ],
                                },
                                "minItems": 1,
                                "maxItems": 2,
                            },
                        },
                        "required": ["user_message", "objectives"],
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
{"name":"get_product_details","arguments":{"product_name": "Lung"}}
{"name":"get_product_property","arguments":{"property": "ingredients"}}
{"name":"get_product_property","arguments":{"property": "target_audience", "product_name": ""}}
{"name":"get_product_property","arguments":{"property": "application_area", "product_name": "Omega 3 plus"}}
{"name":"get_products_by_property", "arguments":{"property": "target_audience", "objectives": ["Sportler"], "user_message": "Für wen ist das Produkt gut?"}
{"name":"get_products_by_property", "arguments":{"property": "application_area", "objectives": ["Kopfschmerz"], "user_message": ""}
{"name":"get_qna_answer","arguments":{"user_message": "Sind die Produkte von Ethno Health vegetarisch?"}}

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

        end_time = time.perf_counter()
        duration = end_time - start_time

        print("================================================")
        print("------------ Tool search query -----------------")
        print(f"- User: {__user__['name']}")
        print(f"- Model: {response.model}")
        print(f"- User message: {user_message}")
        print(f"- Context product: {self.context_product}")
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

        if "objectives" in arguments and function_name != "get_products_by_property":
            del arguments["objectives"]

        if function_name == "get_product_property" and "user_message" in arguments:
            del arguments["user_message"]

        if function_name == "get_product_list":
            arguments = {}

        print(f"- Function name: {function_name}")
        print(f"- Arguments: {arguments}")

        if function_name in handlers:
            db_query_start = time.perf_counter()
            result = handlers[function_name](**arguments)
            end_time = time.perf_counter()
        else:
            return response

        print("================================================")
        print(f"Tool search time: {duration:.1f} s")
        print(f"DB query duration: {end_time - db_query_start:.1f} s")
        print(f"Total tool time: {end_time - start_time:.1f} s")
        print("================================================")

        prompt = ""
        user_content = user_message
        if result:
            prompt = result.get("prompt", "")
            data = result.get("data", "")
            context = f"\n\n<context>\n{data}\n</context>\n\n"
            user_content = f"{context}{prompt}{user_message}\n\n"
            # (
            #     f"{context}Render all products from the context.\n\n"
            #     if isinstance(data, list) and len(data)
            #     else f"{context}{user_message}\n\n"
            # )
            print(f"Function call result: {result.get('data', '')}")
            print("================================================")

        elif function_name:
            prompt = self.valves.PROMPT_NOTHING_FOUND
            context = ""

        # print(f"------> propmpt: {prompt}")
        # print(f"------> user_content: {user_content}")
        messages = [
            {
                "role": "system",
                "content": f"""                
                {parse_template(system_message, ["username"], {"username": username})}
                """,
            },
            {
                "role": "user",
                "content": user_content,
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
                    extra_body={"top_k": 3},
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
                    break

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
