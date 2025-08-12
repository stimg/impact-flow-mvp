import requests, psycopg2
import tools_schema
from psycopg2.extras import RealDictCursor
from typing import Literal

API_BASE_URL=
TOOLS_MODEL_ID = "qwen/qwen3-72B-instruct"
EMBEDDING_MODEL_ID = "bge-m3"

def generate_embedding(self, text):
    res = requests.request(
        method="POST",
        url=f"{API_BASE_URL}/embed",
        headers={
            "Content-Type": "application/json",
        },
        json={
            "model": EMBEDDING_MODEL_ID,
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

def query_db(self, query):
    """
    Queries the PostgreSQL database using the provided user message.
    For example, it searches for a matching answer in the FAQ table.
    """
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DATABASE,
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(query)
        results = cur.fetchall()
        cur.close()
        conn.close()

        if not results:
            return "No matching product found in the database."

        return results

    except Exception as e:
        return f"Database error: {e}"

def get_product_list(self):
    """
    Queries the PostgreSQL database.
    It searches for all available products in the database.
    """
    query = """
            SELECT
                product_id,
                jsonb_object_agg(
                        vmetadata->>'section',
                        chunk_text
                ) AS info
            FROM product_chunks
            WHERE vmetadata->>'section' IN ('name', 'categories', 'short_description', 'reference_link')
            GROUP BY product_id
            LIMIT 10 \
            """

    results = query_db(query)

    return {
        "prompt": PROMPT_LIST,
        "data": [
            {
                "Produktinfo": item["info"],
            }
            for item in results
        ],
    }

def get_category_list(self):
    """
    Queries the PostgreSQL DB for the list of all available categories.
    """
    query = f"""
            WITH categories AS (
                SELECT product_id, substring(chunk_text FROM 'Kategorien: (.*)') AS category
                FROM product_chunks
                WHERE vmetadata->>'section' = 'categories'
            ),
                 tags AS (
                     SELECT product_id, unnest(string_to_array(substring(chunk_text FROM 'Schlagworte: (.*)'), ', ')) AS tag
                     FROM product_chunks
                     WHERE vmetadata->>'section' = 'tags'
                 )
            SELECT
                c.category,
                ARRAY_AGG(DISTINCT t.tag) AS tags
            FROM categories c
                     JOIN tags t ON t.product_id = c.product_id
            GROUP BY c.category
            ORDER BY c.category
        """
    results = query_db(query)
    # print(f"---------> results: {results}")
    # categories = [f"{result['category']}" for result in results]

    data = [
        {"category": {result["category"]}, "tags": {tag for tag in result["tags"]}}
        for result in results
    ]

    # print(f"---------> data: {data}")

    return {
        "prompt": """
            Render categories **as a list**.
            Every category name **must be** rendered in **bold**
            After every category in the same line render 
            - em dash
            - the comma separated tag list in the parentheses rendered in *italic*
            """,
        "data": data,
    }

def get_products_by_category(self, category: str):
    """
    Queries the PostgreSQL database using the optional categories list.
    For example, it searches for all available products in the category or database.
    """
    if not category:
        return {"prompt": "", "data": "Category is not defined"}

    vector_category = generate_embedding(category)

    query = f"""
            SELECT
                product_id,
                jsonb_object_agg(
                    vmetadata->>'section',
                    chunk_text
                ) AS info
            FROM product_chunks
            WHERE product_id IN (
                SELECT product_id
                FROM product_chunks
                WHERE chunk_text IN (
                    SELECT chunk_text
                    FROM product_chunks
                    WHERE vmetadata->>'section' = 'categories'
                    ORDER BY embedding <#> '{vector_category}'
                    LIMIT 2
                )
            )
            AND vmetadata->>'section' IN ('name', 'categories', 'short_description', 'reference_link')
            GROUP BY product_id
        """

    results = query_db(query)
    return {
        "prompt": (
            PROMPT_LIST
            if len(results) > 1
            else f"{PROMPT_DETAILS}{PROMPT_FOOTER}"
        ),
        "data": [
            {
                "Produktinfo": item["info"],
            }
            for item in results
        ],
    }

def get_products_by_property(self, property: str, user_message: str):
    """
    Queries the PostgreSQL database using the optional categories list.
    For example, it searches for all available products in the category or database.
    """

    prop = property if property != "application_area" else "tags"

    vector = generate_embedding(user_message)

    query = f"""
            SELECT
                product_id,
                jsonb_object_agg(
                    vmetadata->>'section',
                    chunk_text
                ) AS info
            FROM product_chunks
            WHERE product_id IN (
                SELECT product_id
                FROM product_chunks
                WHERE vmetadata->>'section' = '{prop}'
                AND chunk_text <> ''
                AND abs(embedding <#> '{vector}') > 0.4
                ORDER BY abs(embedding <#> '{vector}') DESC
                LIMIT 5
            )
            AND vmetadata->>'section' IN ('name', '{property}', 'reference_link')
            GROUP BY product_id
        """

    results = query_db(query)
    print(f"----> Results: {results}")
    print(f"----> Results type: {type(results)}")

    if isinstance(results, str):
        print(f"-------> STRING!!")
        return {"prompt": "", "data": "No products found."}

    return {
        "prompt": (
            PROMPT_LIST
            if len(results) > 1
            else f"{PROMPT_DETAILS}{PROMPT_FOOTER}"
        ),
        "data": [
            {
                "Produktinfo": item["info"],
            }
            for item in results
        ],
    }

def get_product_details(self, product_name):
    """
    Queries the PostgreSQL database using the provided product name.
    For example, it searches for a matching product in the database.
    """
    if not product_name:
        return {"prompt": "", "data": "Product is not defined"}

    # print(f"-----> product_name: {product_name}")

    vector = generate_embedding(product_name)

    query = f"""
            SELECT
                product_id,
                jsonb_object_agg(
                    vmetadata->>'section',
                    chunk_text
                ) AS product_info
            FROM product_chunks
            WHERE product_id IN (
                SELECT product_id
                FROM product_chunks
                WHERE vmetadata->>'section' = 'name'
                ORDER BY embedding <#> '{vector}'
                LIMIT 1
            )
            GROUP BY product_id
        """

    results = query_db(query)
    # print(f"Results: {results}")

    if not results:
        return "No matching product found in the database."

    product_info = results[0]["product_info"]

    # print(f"Produkt details: {product_info}")

    return {
        "prompt": f"{PROMPT_DETAILS}{PROMPT_FOOTER}",
        "data": {
            "product_id": str(results[0]["product_id"]),
            **product_info,
        },
    }

Property = Literal[
    "target_audience",
    "intake_recommendation",
    "application_area",
    "ingredients",
    "formulation_origin",
    "history",
    "user_experience",
]

def get_product_property(self, property: Property, product_name=""):
    """
    Queries the PostgreSQL database for the product property using the provided product property.
    For example, when the user asks about the specific product property
    like target group, application area, user feedback, ingredients, etc.
    """
    # print(f"-----> product_name param: {product_name}")

    name = product_name or context_product.get("name", "")

    # print(f"-----> property: {property}")
    # print(f"-----> context product: {context_product}")
    # print(f"-----> product_name: {name}")

    if not property or not name:
        return {"prompt": "", "data": "Product or property name is not defined."}

    vector_property = generate_embedding(property)
    vector_name = generate_embedding(f"Poduktname: {name}")

    query = f"""
            SELECT vmetadata,
                chunk_text
                AS info
            FROM product_chunks
            WHERE product_id IN (SELECT product_id
                FROM product_chunks
                WHERE vmetadata ->> 'section' = 'name'
                ORDER BY embedding <#> '{vector_name}'
                LIMIT 1)
            AND vmetadata ->> 'section' = '{property}'
        """

    results = query_db(query)
    # print(f"-----> Results: {results}")

    if not results:
        return "No matching product found in the database."

    name = results[0]["vmetadata"]["name"]
    url = results[0]["vmetadata"]["reference_link"]

    if product_name and context_product.get("name", "") != product_name:
        context_product = {"name": name, "url": url}

    return {
        "prompt": f"{PROMPT_PROPERTY}{PROMPT_FOOTER}",
        "data": {
            "Produktname": name,
            "Produktwebseite": url,
            "Antwort des Assistenten": results[0]["info"],
        },
    }

def get_qna_answer(self, topic, user_message):
    """Queries the PostgreSQL Q&A database for the related disclaimer
    if the user asks questions about pregnancy, medicines, or other stuff, not directly connected to the product properties.
    Examples:
    - Darf das Produkt bei Einnahme von Medikamenten eingenommen werden?
    - Darf ich das Produkt nutzen, wenn ich andere Medikamenten einnehme?
    - Kann ich das produkt während der Schwangerschaft konsumieren?
    - Gibt es Kontraindikationen bei der Einnahme vom Produkt?
    """

    if not user_message:
        return {"prompt": "", "data": "User message is not defined"}

    # print(f"--------> User message: {user_message}")
    query_vector = generate_embedding(user_message)

    query = f"""
            SELECT answer_text
            FROM q_and_a
            WHERE vmetadata ->> 'topic' = '{topic}'
            ORDER BY q_embedding <#> '{query_vector}'
            LIMIT 1
        """
    results = query_db(query)
    # print(f"-----> Results: {results}")

    if not results:
        return {
            "prompt": "",
            "data": {
                "Answer": "There is no suitable answer in our database. Please contact our customer service.",
            },
        }

    if topic == "general" or not context_product:
        name = "Ethno Health"
        url = "https://www.ethno-health.com"
        prompt = PROMPT_QNA
    else:
        name = context_product.get("name", "")
        url = context_product.get("url", "")
        prompt = PROMPT_PROPERTY

    return {
        "prompt": f"{prompt}{PROMPT_FOOTER}",
        "data": {
            "Produktname": name,
            "Produktwebseite": url,
            "Antwort": f"{results[0]['answer_text']}",
        },
    }

### Tools implemenatation

def get_user_experience(self, product_name=""):
    """
    Queries the PostgreSQL database for the user feedback, usage, and user experience for the product with the given name.
    Use it when the user asks questions about product usage and user experience ans stories by using the product.
    Examples:
    - What do the people say about the product?
    - Are there any user stories about the product usage and results?
    - How do the users rate the product?
    - Do you have any user opinions about the product?

    "Ethno Health **CAN NOT BE** the product name"
    """

    return get_product_property("user_experience", product_name)

def get_product_ingredients(self, product_name=""):
    """
    Queries the PostgreSQL database for the particular product ingredients.
    Use it when the context product is defined and the user asks a concrete question about the particular product.

    **DO NOT** use it when the user asks common questions about 'Ethno Health' products
    immune system support, vitality, selected ingredients, quality standards,
    product quality, sustainable sourcing, environmental protection,
    global communities, Ethno Health, natural ingredients, health supplements.
    """

    return get_product_property("ingredients", product_name)

def get_product_application_area(self, product_name=""):
    """
    Queries the PostgreSQL database for the particular product application area.
    Use it when the context product is defined and the user asks a concrete
    question about the particular product applications.
    Examples:
    - What is this product for?
    - Is the product suitable for losing weight?
    - Can this product improve concentration?

    **DO NOT** use it when the user asks common questions about 'Ethno Health' products
    immune system support, vitality, selected ingredients, quality standards,
    product quality, sustainable sourcing, environmental protection,
    global communities, Ethno Health, natural ingredients, health supplements."""

    return get_product_property("application_area", product_name)

def get_intake_recommendation(self, product_name=""):
    """
    Queries the PostgreSQL database for the intake recommendations.
    """
    return get_product_property("intake_recommendation", product_name)

def get_target_audience(self, product_name=""):
    """
    Queries the PostgreSQL database for the target people groups and matching audience.
    """
    return get_product_property("target_audience", product_name)

def get_formulation_origin(self, product_name=""):
    """
    Queries the PostgreSQL database for the recipe or formulation origin.
    """
    return get_product_property("formulation_origin", product_name)

def get_product_history(self, product_name=""):
    """
    Queries the PostgreSQL database for the history of the product creation, its author, country, circumstances, origin, or invention.

    *USE IT* when the user asks about a **particular historical** product background.

    **DO NOT USE** it when the user asks question about **Ethno Health* product production, special features, quality standards, or product requirements.
    """
    return get_product_property("history", product_name)

def get_disclaimer(self, user_message):
    """
    Queries the PostgreSQL Q&A database for the related disclaimer if the user asks questions about pregnancy, medicines, or other stuff, not directly connected to the product properties.
    Examples:
    - How does essence aminos affect the skin during pregnancy?
    - Can I consume the product during pregnancy?
    - Can pregnant women use Ethno Health products?
    - Can the product be taken while using medication?
    - May I use the product if I am taking other medications?
    - Are there any contraindications for taking the product?
    """

    if not user_message:
        return {"prompt": "", "data": "User message is not defined"}

    return get_qna_answer("disclaimer", user_message)

def get_general_info(self, user_message):
    """Queries the PostgreSQL Q&A database for the related information if the user asks questions
    about the **Ethno Health** products, quality, brand, traditional knowledge, research, nutrition,
    sustainable nutrition, vegan products, natural ingredients, immune system support, vitality boost,
    traditional medicine, modern science, well-being, plant-based nutrients,
    not directly connected to the product properties.
    Examples:
    - I have heard that dietary supplements are sometimes viewed critically. What makes Ethno Health’s products special?
    - Are Ethno Health’s products suitable for vegetarians and vegans?
    - How do vegetarians and vegans benefit from the comprehensive product range offered by Ethno Health?
    - How does Ethno Health promote sustainability in sourcing its ingredients?
    - What quality standards does Ethno Health meet in the production of its products?
    - How does Ethno Health help support health?
    """
    if not user_message:
        return {"prompt": "", "data": "User message is not defined"}

    return get_qna_answer("general", user_message)

tools = [
    get_product_list,
    get_category_list,
    get_product_details,
    get_products_by_category,
    # get_products_by_application,
    get_products_by_property,
    get_user_experience,
    get_product_ingredients,
    get_product_application_area,
    get_intake_recommendation,
    get_target_audience,
    get_formulation_origin,
    get_product_history,
    get_disclaimer,
    get_general_info,
]

handlers = {
    "get_product_list": get_product_list,
    "get_category_list": get_category_list,
    "get_products_by_category": get_products_by_category,
    # "get_products_by_application": get_products_by_application,
    "get_products_by_property": get_products_by_property,
    "get_product_details": get_product_details,
    "get_user_experience": get_user_experience,
    "get_product_ingredients": get_product_ingredients,
    "get_product_application_area": get_product_application_area,
    "get_intake_recommendation": get_intake_recommendation,
    "get_target_audience": get_target_audience,
    "get_formulation_origin": get_formulation_origin,
    "get_product_history": get_product_history,
    "get_disclaimer": get_disclaimer,
    "get_general_info": get_general_info,
}

