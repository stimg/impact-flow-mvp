from pydantic import BaseModel, Field
import json, requests, re, time, psycopg2
import numpy as np
from ollama import Client
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from typing import Literal


class Pipe:
    class Valves(BaseModel):
        RAG_MODEL_ID: str = Field(
            default="qwen/qwen3-8b-fp8",
            description="Model to use for RAG.",
        )
        TOOLS_MODEL_ID: Literal["qwen2.5:3b"] = Field(
            default="qwen2.5:3b",
            description="Model to use for the tools selection.",
        )
        EMBEDDING_MODEL_ID: str = Field(
            default="bge-m3",
            description="Model to use for embedding generation.",
        )
        PROMPT_LIST: str = Field(
            default="Folgende Punkte immer in einem Block zu rendern: Produktname, Kategorie, Kurzbeschreibung, Produktwebseite im Format [Produktname](https://www.ethno-health.com/artikeldetail/<produkt_link>), ---\n.",
            description="System prompt for product list.",
        )
        PROMPT_DETAILS: str = Field(
            default="Folgende Pukte (wenn verfügbar) zu beachten: Produktname, Produktbeschreibung, Zielgruppe, Anwendung, Vorteile, Produktwebseite im Format [Produktname](https://www.ethno-health.com/<produkt_link>) immer zeigen.",
            description="System prompt for product details.",
        )
        PROMPT_PROPERTY: str = Field(
            default="Zeige den Produktname, die gezielte Information über die angefragte Produkteigenschaft und das Link auf der Produktewebseite. Nichts mehr.",
            description="System prompt for product property.",
        )
        PROMPT_QNA: str = Field(
            default="",
            description="System prompt for product property.",
        )
        PROMPT_FOOTER: str = Field(
            default="",
            description="System prompt for template footer.",
        )
        API_BASE_URL: str = Field(
            default="http://localhost:11434/api",
            description="Base URL for accessing Ollama API endpoints.",
        )

        # PostgreSQL connection configuration
        POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host.")
        POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port.")
        POSTGRES_USER: str = Field(
            default="postgres", description="PostgreSQL username."
        )
        POSTGRES_PASSWORD: str = Field(
            default="password", description="PostgreSQL password."
        )
        POSTGRES_DATABASE: str = Field(
            default="postgres", description="PostgreSQL database name."
        )

    ollama = Client(
        host="http://localhost:11434",
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
    )

    openai = OpenAI(
        base_url="https://api.novita.ai/v3/openai",
        api_key="sk_0d9bk8e4VZs0EWckVnT0FnkTUNJW4iqvRtodgLEN-Ec",
    )

    context_product = {}

    def __init__(self):
        self.valves = self.Valves()

    def generate_embedding(self, text):
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

    def query_db(self, query):
        """
        Queries the PostgreSQL database using the provided user message.
        For example, it searches for a matching answer in the FAQ table.
        """
        try:
            conn = psycopg2.connect(
                host=self.valves.POSTGRES_HOST,
                port=self.valves.POSTGRES_PORT,
                user=self.valves.POSTGRES_USER,
                password=self.valves.POSTGRES_PASSWORD,
                database=self.valves.POSTGRES_DATABASE,
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
            LIMIT 10
        """

        results = self.query_db(query)

        return {
            "prompt": self.valves.PROMPT_LIST,
            "data": [
                {
                    "Produktinfo": item["info"],
                }
                for item in results
            ],
        }

    def get_category_list(self):
        return {
            "prompt": "",
            "data": [
                "Body & Clean",
                "Vitality & Family",
                "Omega-Öle & Vitalkomplex",
                "Omega Go!, Omega-Öle & Vitalkomplex",
                "Shape Classic, Shape Weight Management",
                "Tibetische Rezeptur Lung",
            ],
        }

    def get_products_by_category(self, category: str):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """
        if not category:
            return {"prompt": "", "data": "Category is not defined"}

        vector_category = self.generate_embedding(category)

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

        results = self.query_db(query)
        return {
            "prompt": (
                self.valves.PROMPT_LIST
                if len(results) > 1
                else f"{self.valves.PROMPT_DETAILS}{self.valves.PROMPT_FOOTER}"
            ),
            "data": [
                {
                    "Produktinfo": item["info"],
                }
                for item in results
            ],
        }

    def get_products_by_property(self, property: str, context: str):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """
        # print(f"-----> property: {property}")
        # print(f"-----> context: {context}")

        vector = self.generate_embedding(context)

        # print(f"\n-----> vector: {vector}\n")

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
                WHERE vmetadata->>'section' = '{property}'
                ORDER BY embedding <#> '{vector}'
                LIMIT 3
            )
            AND vmetadata->>'section' IN ('name', 'categories', 'short_description', 'reference_link')
            GROUP BY product_id
        """

        results = self.query_db(query)
        return {
            "prompt": (
                self.valves.PROMPT_LIST
                if len(results) > 1
                else f"{self.valves.PROMPT_DETAILS}{self.valves.PROMPT_FOOTER}"
            ),
            "data": [
                {
                    "Produktinfo": item["info"],
                }
                for item in results
            ],
        }

    def get_products_by_application(self, context):
        """
        Queries the PostgreSQL database for the application and use cases.
        For example, it searches for something for muscle building or concentration, against cough or headache.
        """
        return self.get_products_by_property("application_area", context)

    def get_product_details(self, product_name):
        """
        Queries the PostgreSQL database using the provided product name.
        For example, it searches for a matching product in the database.
        """
        if not product_name:
            return {"prompt": "", "data": "Product is not defined"}

        # print(f"-----> product_name: {product_name}")

        vector = self.generate_embedding(product_name)

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

        results = self.query_db(query)
        # print(f"Results: {results}")

        if not results:
            return "No matching product found in the database."

        product_info = results[0]["product_info"]

        # print(f"Produkt details: {product_info}")

        return {
            "prompt": f"{self.valves.PROMPT_DETAILS}{self.valves.PROMPT_FOOTER}",
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
        print(f"-----> product_name param: {product_name}")

        name = product_name or self.context_product.get("name", "")

        # print(f"-----> property: {property}")
        # print(f"-----> product_name: {name}")

        if not property or not name:
            return {"prompt": "", "data": "Product or property name is not defined."}

        vector_property = self.generate_embedding(property)
        vector_name = self.generate_embedding(f"Poduktname: {name}")

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

        results = self.query_db(query)
        # print(f"-----> Results: {results}")

        if not results:
            return "No matching product found in the database."

        name = results[0]["vmetadata"]["name"]
        url = results[0]["vmetadata"]["reference_link"]

        if product_name and self.context_product.get("name", "") != product_name:
            self.context_product = {"name": name, "url": url}

        return {
            "prompt": f"{self.valves.PROMPT_PROPERTY}{self.valves.PROMPT_FOOTER}",
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
        query_vector = self.generate_embedding(user_message)

        query = f"""
            SELECT answer_text
            FROM q_and_a
            WHERE vmetadata ->> 'topic' = '{topic}'
            ORDER BY q_embedding <#> '{query_vector}'
            LIMIT 1
        """
        results = self.query_db(query)
        # print(f"-----> Results: {results}")

        if not results:
            return {
                "prompt": "",
                "data": {
                    "Answer": "There is no suitable answer in our database. Please contact our customer service.",
                },
            }

        if topic == "general" or not self.context_product:
            name = "Ethno Health"
            url = "https://www.ethno-health.com"
            prompt = self.valves.PROMPT_QNA
        else:
            name = self.context_product.get("name", "")
            url = self.context_product.get("url", "")
            prompt = self.valves.PROMPT_PROPERTY

        return {
            "prompt": f"{prompt}{self.valves.PROMPT_FOOTER}",
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

        return self.get_product_property("user_experience", product_name)

    def get_product_ingredients(self, product_name=""):
        """
        Queries the PostgreSQL database for the particular product ingredients.
        Use it when the context product is defined and the user asks a concrete question about the particular product.

        **DO NOT** use it when the user asks common questions about 'Ethno Health' products
        immune system support, vitality, selected ingredients, quality standards,
        product quality, sustainable sourcing, environmental protection,
        global communities, Ethno Health, natural ingredients, health supplements.
        """

        return self.get_product_property("ingredients", product_name)

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

        return self.get_product_property("application_area", product_name)

    def get_intake_recommendation(self, product_name=""):
        """
        Queries the PostgreSQL database for the intake recommendations.
        """
        return self.get_product_property("intake_recommendation", product_name)

    def get_target_audience(self, product_name=""):
        """
        Queries the PostgreSQL database for the target people groups and matching audience.
        """
        return self.get_product_property("target_audience", product_name)

    def get_formulation_origin(self, product_name=""):
        """
        Queries the PostgreSQL database for the recipe or formulation origin.
        """
        return self.get_product_property("formulation_origin", product_name)

    def get_product_history(self, product_name=""):
        """
        Queries the PostgreSQL database for the history of the product creation, its author, country, circumstances, origin, or invention.

        *USE IT* when the user asks about a **particular historical** product background.

        **DO NOT USE** it when the user asks question about **Ethno Health* product production, special features, quality standards, or product requirements.
        """
        return self.get_product_property("history", product_name)

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

        return self.get_qna_answer("disclaimer", user_message)

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

        return self.get_qna_answer("general", user_message)

    ### --- PIPE funciton ---
    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for a related answer,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")
        # print(f"\nBody: {body}\n")

        # Extract the product from the last message.
        messages = body.get("messages", [])
        # print(f"\nMessages: {messages}\n")

        if not messages:
            return "No messages provided in the request body."

        for message in messages:
            if message.get("role", "") == "system":
                system_message = message.get("content", "")
                # print(f"\n---------> System message: {system_message}\n\n")

            if message.get("role", "") == "assistant":
                assistant_message = message.get("content", "")
                # print(f"\n---------> Assistant message: {system_message}\n\n")

                pattern_name = r"^\s*\**Produktname:\s(.+?)\**$"
                pattern_url = r"https:\/\/www\.ethno-health\.com\/artikeldetail[^)]+"
                match_name = re.match(pattern_name, assistant_message, re.MULTILINE)
                match_url = re.search(pattern_url, assistant_message, re.MULTILINE)
                # print(f"-----> Match name: {match_name}")
                # print(f"-----> Match url: {match_url}")

                if match_name:
                    self.context_product = {
                        "name": match_name.group(1) if match_name else "",
                        "url": match_url.group() if match_url else "",
                    }
                    # print(
                    #    f"---------> Context product from history: {self.context_product}"
                    # )

            if message.get("role", "") == "user":
                user_message = message.get("content", "")
                user_message = re.sub(r"\s[!?\.]", "", user_message)
                # print(f"---------> User message: {user_message}")

        # Define variables for LLM
        tools = [
            self.get_product_list,
            self.get_category_list,
            self.get_product_details,
            self.get_products_by_category,
            # self.get_products_by_application,
            self.get_user_experience,
            self.get_product_ingredients,
            self.get_product_application_area,
            self.get_intake_recommendation,
            self.get_target_audience,
            self.get_formulation_origin,
            self.get_product_history,
            self.get_disclaimer,
            self.get_general_info,
        ]

        handlers = {
            "get_product_list": self.get_product_list,
            "get_category_list": self.get_category_list,
            "get_products_by_category": self.get_products_by_category,
            # "get_products_by_application": self.get_products_by_application,
            "get_product_details": self.get_product_details,
            "get_user_experience": self.get_user_experience,
            "get_product_ingredients": self.get_product_ingredients,
            "get_product_application_area": self.get_product_application_area,
            "get_intake_recommendation": self.get_intake_recommendation,
            "get_target_audience": self.get_target_audience,
            "get_formulation_origin": self.get_formulation_origin,
            "get_product_history": self.get_product_history,
            "get_disclaimer": self.get_disclaimer,
            "get_general_info": self.get_general_info,
        }

        product_name_parameter = {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name extracted from the context",
                },
            },
            "required": ["product_name"],
        }

        opt_product_name_parameter = {
            "type": "object",
            "properties": {
                "product_name": {
                    "type": "string",
                    "description": "Product name extracted from the context",
                }
            },
        }

        target_context_parameter = {
            "type": "object",
            "properties": {
                "target_context": {
                    "type": "string",
                    "description": "Target or expected context product usage extracted from the user request",
                }
            },
            "required": ["target_context"],
        }

        user_message_parameter = {
            "type": "object",
            "properties": {
                "user_message": {
                    "type": "string",
                    "description": "User message",
                }
            },
            "required": ["user_message"],
        }

        no_parameters = {"type": "object", "properties": {}}

        property_parameter = {
            "type": "object",
            "properties": {
                "property": {
                    "type": "string",
                    "description": "Product property extracted from user message",
                    "enum": [
                        "target_audience",
                        "intake_recommendation",
                        "application_area",
                        "ingredients",
                        "formulation_origin",
                        "history",
                        "user_experience",
                    ],
                }
            },
            "required": ["property"],
        }

        """
                {
                    "name": "get_products_by_application",
                    "description": "Searches for the application and use cases like something for muscle building or concentration, against cough or headache, etc.",
                    "parameters": target_context_parameter,
                },
        """
        tools_schema = json.dumps(
            [
                {
                    "name": "get_product_list",
                    "description": "Fetches a list of products. Use when the user asks about available products.",
                },
                {
                    "name": "get_category_list",
                    "description": """
                        Queries the PostgreSQL DB for a list of categories.
                        Examples:
                        - Which categories do you have?

                    **DO NOT** use it when user asks about products in the particular category.
                    """,
                },
                {
                    "name": "get_products_by_category",
                    "description": """
                        Fetches a list of products in the category. Use when the user asks about products in the particular category.
                        Examples:
                        - Which products do you have in the Body & Clean category?
                        - Show me the products from the Vitality & Family.
                    """,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "category": {
                                "type": "string",
                                "description": "Category",
                            }
                        },
                        "required": ["category"],
                    },
                },
                {
                    "name": "get_product_details",
                    "description": "Fetches detailed information about a product. Use when the user refers to a specific product by name, but **there is no specific product property** in the request.",
                    "parameters": product_name_parameter,
                },
                {
                    "name": "get_disclaimer",
                    "description": """
                        Queries the PostgreSQL Q&A database for the related disclaimer if the user asks questions about pregnancy, medicines, or other stuff, not directly connected to the product properties.
                        Examples:
                        - How does essence aminos affect the skin during pregnancy?
                        - Can I consume the product during pregnancy?
                        - Can pregnant women use Ethno Health products?
                        - Can the product be taken while using medication?
                        - May I use the product if I am taking other medications?
                        - Are there any contraindications for taking the product?
                    """,
                    "parameters": user_message_parameter,
                },
                {
                    "name": "get_general_info",
                    "description": """Queries the PostgreSQL Q&A database for the related information.
                        Use it if the user asks general questions about the **Ethno Health** products, 
                        quality, brand, traditional knowledge, research, nutrition, sustainable nutrition, 
                        vegan products, natural ingredients, immune system support, vitality boost,
                        traditional medicine, modern science, well-being, plant-based nutrients,
                        not directly connected to the product properties.
                        
                        **DO USE** it if there is the 'Ethno Health' string in the user message.
                        
                        Examples:
                        - I have heard that dietary supplements are sometimes viewed critically. What makes Ethno Health’s products special?
                        - Are Ethno Health’s products suitable for vegetarians and vegans?
                        - How do vegetarians and vegans benefit from the comprehensive product range offered by Ethno Health?
                        - How does Ethno Health promote sustainability in sourcing its ingredients?
                        - What quality standards does Ethno Health meet in the production of its products?
                        - How does Ethno Health help support health?
                        - Wie unterstützt Ethno Health die Nachhaltigkeit bei der Beschaffung seiner Zutaten?
                    """,
                    "parameters": user_message_parameter,
                },
                ### Produkt props
                {
                    "name": "get_user_experience",
                    "description": """
                        Queries the PostgreSQL database for the user feedback, usage, and user experience for the product with the given name.
                        Use it when the user asks questions about product usage and user experience ans stories by using the product.
                        Examples:
                        - What do the people say about the product?
                        - Are there any user stories about the product usage and results?
                        - How do the users rate the product?
                        - Do you have any user opinions about the product?
                    """,
                },
                {
                    "name": "get_product_ingredients",
                    "description": """
                        Queries the PostgreSQL database for the particular product ingredients.
                        Use it when the context product is defined and the user asks a concrete question about the particular product.
                    """,
                },
                {
                    "name": "get_product_application_area",
                    "description": """
                        Queries the PostgreSQL database for the particular product application area.
                        Examples:
                        - What is this product for?
                        - Is the product suitable for losing weight?
                        - Can this product improve concentration?
                    """,
                },
                {
                    "name": "get_intake_recommendation",
                    "description": "Queries the PostgreSQL database for the particular product intake recommendations.",
                },
                {
                    "name": "get_target_audience",
                    "description": "Queries the PostgreSQL database for the particular product target people group and matching audience.",
                },
                {
                    "name": "get_formulation_origin",
                    "description": "Queries the PostgreSQL database for the particular product recipe or formulation origin.",
                },
                {
                    "name": "get_product_history",
                    "description": """
                        Queries the PostgreSQL database for the history of the particular product creation, its author, country, circumstances, origin, or invention.
                    """,
                },
            ]
        )

        # print(f"--> tools_schema:\n{tools_schema}")
        system_prompt_tools = (
            """
You are a product assistant.
Respond *only* with valid JSON, no explanations.

You have access to the following tools:

"""
            + tools_schema
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
{"name":"get_product_details","arguments":{"product_name":"Lung"}}
{"name":"get_product_ingredients","arguments":{}}
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

        start_time = time.perf_counter()

        """
        response = self.ollama.chat(
            model=self.valves.TOOLS_MODEL_ID,
            messages=messages,
            tools=tools,
            format="json",
            options={
                "num_ctx": 4096,
                "top_k": 1,
                "top_p": 0.7,
                "temperature": 0,
            },
        )
        """
        response = self.openai.chat.completions.create(
            model="qwen/qwen2.5-7b-instruct",
            messages=messages,
            stream=False,
            # tools=tools, ## qwen can't
            temperature=0,
        )

        end_time = time.perf_counter()
        duration = end_time - start_time
        print("================================================")
        print(f"Tool search time: {duration:.1f} seconds")
        print("================================================")

        # print(f"------------> response: {response}")

        # Catch Ollama and OpenAI response format diffs

        # print(f"------------> content: {content}")

        if hasattr(response, "choices"):
            content = response.choices[0].message.content
        else:
            content = response["message"]["content"]

        ### Statistic
        print("--- Tool search query ---")
        print(f"- Model: {response.model}")
        if "total_duration" in response:
            # print(f"- Load duration: {(response.load_duration / 1e9):.1f}s")
            # print(f"- Eval count: {response.eval_count}")
            # print(f"- Eval duration: {(response.eval_duration / 1e9):.1f}s")
            print(f"- Prompt eval count: {response.prompt_eval_count}")
            print(
                f"- Prompt eval duration: {(response.prompt_eval_duration / 1e9):.1f}s"
            )
            print(f"- Total duration: {(response.total_duration / 1e9):.1f}s")
        elif "usage" in response:
            print(f"- Prompt tokens: {(response.usage['prompt_tokens'] / 1e9):.1f}s")
            print(f"- Total tokens: {(response.usage['total_tokens'] / 1e9):.1f}s")
        print("---------------------")

        # print(f"Function search response: {response}")

        function_name = ""
        arguments = {}
        result = {}
        if "tool_calls" in message:
            print(f"--- Tool call ---")
            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            arguments = tool_call.function.arguments
        else:
            content = json.loads(content)
            print(f"--- No tool call ---")

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

        print(f"- Context product: {self.context_product}")
        print(f"- Function name: {function_name}")
        print(f"- Arguments: {arguments}")
        print(f"- User message: {user_message}")
        print("-------------------")

        try:
            if (
                "product_name" in arguments
                and arguments["product_name"] == "Ethno Health"
            ):
                result = handlers["get_general_info"](user_message)
            else:
                if function_name in handlers:
                    result = handlers[function_name](**arguments)

        except NameError as e:
            result = {"prompt": "", "data": e}

        if result:
            print(f"Function call result: {result.get('data', '')}")
            print("-------------------")

        messages = [
            {
                "role": "system",
                "content": f"""{system_message}\n\n{result.get('prompt', '')}\n\nContext:\n\n{result.get('data', '')}""",
            },
            {
                "role": "user",
                "content": f"/no_think {user_message}",
            },
        ]

        # print(f"\nMessages: {messages}\n")

        try:
            start_time = time.perf_counter()

            for chunk in self.openai.chat.completions.create(
                model=self.valves.RAG_MODEL_ID,
                messages=messages,
                stream=True,
                max_tokens=8192,
            ):
                choice = chunk.choices[0]
                if choice.finish_reason == "stop":
                    print(f"- Model: {chunk.model}")
                    if chunk.usage:
                        print(f"- Prompt tokens: {chunk.usage.prompt_tokens}")
                        print(f"- Completion tokens: {chunk.usage.completion_tokens}")
                        print(f"- Total tokens: {chunk.usage.total_tokens}")
                response = choice.delta.content or ""
                # print(f"Response: {response}")
                yield response

            end_time = time.perf_counter()
            duration = end_time - start_time
            print("================================================")
            print(f"Chat completion processing time: {duration:.1f} seconds")
            print("================================================")

        except Exception as e:
            yield f"Error: {e}"
