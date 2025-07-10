from pydantic import BaseModel, Field
import json, requests
import psycopg2
import numpy as np
from ollama import Client
from psycopg2.extras import RealDictCursor


class Pipe:
    class Valves(BaseModel):
        MODEL_ID: str = Field(
            default="phi4-mini",
            description="Model to use.",
        )
        EMBEDDING_MODEL: str = Field(
            default="bge-m3",
            description="Model to use for embeddings.",
        )
        PROMPT_LIST: str = Field(
            default="Folgende Punkte immer in einem Block zu rendern: Produktname, Kategorie, Kurzbeschreibung, Produktwebseite im Format [Produktname](https://www.ethno-health.com/artikeldetail/<produkt_link>), ---\n.",
            description="System prompt for RAG.",
        )
        PROMPT_DETAILS: str = Field(
            default="Folgende Pukte (wenn verfügbar) zu beachten: Produktname, Produktbeschreibung, Zielgruppe, Anwendung, Vorteile, Produktwebseite im Format [Produktname](https://www.ethno-health.com/<produkt_link>) immer zeigen.",
            description="System prompt for RAG.",
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
                "model": self.valves.EMBEDDING_MODEL,
                "input": text,
                "options": {
                    "top_k": 3,
                    "top_p": 0.3,
                    "temperature": 0.8,
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
                ) AS product_info
            FROM product_chunks
            WHERE vmetadata->>'section' IN ('name', 'categories', 'short_description', 'reference_link')
            GROUP BY product_id;
        """

        results = self.query_db(query)

        return {
            "prompt": self.valves.PROMPT_LIST,
            "data": [
                {
                    "Product ID": item["product_id"],
                    "Produktinfo": item["product_info"],
                }
                for item in results
            ],
        }

    def get_products_by_category(self, category: str):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """
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
                WHERE vmetadata->>'section' = 'categories'
                  AND chunk_text ILIKE '%Body%'
            )
                AND vmetadata->>'section' IN ('name', 'categories', 'short_description', 'reference_link')
            GROUP BY product_id
        """

        results = self.query_db(query)
        return {
            "prompt": (
                self.valves.PROMPT_LIST
                if len(results) > 1
                else self.valves.PROMPT_DETAILS
            ),
            "data": [
                {
                    "Product ID": item["product_id"],
                    **item["product_info"],
                }
                for item in results
            ],
        }

    def get_product_details(self, name):
        """
        Queries the PostgreSQL database using the provided product name.
        For example, it searches for a matching product in the database.
        """
        vector = self.generate_embedding(name)

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

        product_id = results[0]["product_id"]
        product_info = results[0]["product_info"]

        print(f"Produkt details: {product_info}")

        return {
            "prompt": self.valves.PROMPT_DETAILS,
            "data": {
                "product_id": product_id,
                **product_info,
            },
        }

    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for a related answer,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")
        # print(f"Body: {body}")

        # Extract the product from the last message.
        messages = body.get("messages", [])
        # print(f"Messages: {messages}")

        if not messages:
            return "No messages provided in the request body."

        # Get system and user messages
        for message in messages:
            if message.get("role", "") == "system":
                system_message = message.get("content", "")

            if message.get("role", "") == "user":
                user_message = message.get("content", "")

        # Define variables for LLM
        tools = [
            self.get_product_list,
            self.get_product_details,
            self.get_products_by_category,
        ]

        handlers = {
            "get_product_list": self.get_product_list,
            "get_products_by_category": self.get_products_by_category,
            "get_product_details": self.get_product_details,
        }

        tools_schema = json.dumps(
            [
                {
                    "name": "get_product_list",
                    "description": "Fetches a list of products. Use when the user asks about available products.",
                },
                {
                    "name": "get_products_by_category",
                    "description": "Fetches a list of products in the category. Use when the user asks about products in the particular category.",
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
                    "description": "Fetches detailed information about a product. Use when the user refers to a specific product by name.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Product name",
                            }
                        },
                        "required": ["name"],
                    },
                },
            ]
        )

        system_prompt_tools = (
            "You are a product assistant.\n"
            + "Answer directly if you can do so.\n\n"
            + "You have access to the following tools:\n"
            + f"<|tool|>{tools_schema}</|tool|>\n\n"
            + "When needed, call one of the tools.\n\n"
            + "Examples:\n"
            + "User: Welche Produkte hast du im Sortiment hier?\n"
            + 'Assistant: {"function": "get_product_list", "parameters": {}}\n\n'
            + "User: Welche Produkte in der Kategorie Body & Clean hast du?\n"
            + 'Assistant: {"function": "get_product_list", "parameters": {"category": "Body & Clean"}}\n\n'
            + "User: Was weisst du über das Lung Produkt?\n"
            + 'Assistant: {"function": "get_product_details", "parameters": {"name": "Lung"}}\n\n'
        )

        response = self.ollama.chat(
            model="phi4-mini",
            messages=[
                {"role": "system", "content": system_prompt_tools},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            format="json",
        )

        print(f"Function search response: {response}")

        content = json.loads(response["message"]["content"])

        if not content:
            return "No handler defined for this tool call."

        # LLMs give different responses by tool search
        if "function" in content:
            name = content["function"]
            parameters = content["parameters"]
        else:
            for key, value in content.items():
                if (
                        isinstance(value, dict)
                        and "function" in value
                        and "parameters" in value
                ):
                    name = value["function"]
                    parameters = value["parameters"]
                    break

        print(f"Function: {name}")
        print(f"Parameters: {parameters}")

        result = handlers[name](**parameters)
        print(f"Function call result: {result}")

        messages = [
            {
                "role": "system",
                "content": f"{system_message}\n\n{result['prompt']}\n\nContext: {result['data']}",
            },
            {"role": "user", "content": user_message},
        ]

        try:
            for chunk in self.ollama.chat(
                model=self.valves.MODEL_ID,
                messages=messages,
                stream=True,
                format="",
                options={
                    "num_ctx": body.get("num_ctx", 8196),
                    "top_k": body.get("top_k", 5),
                    "top_p": body.get("top_p", 0.9),
                    "max_tokens": body.get("max_tokens", 2048),
                    "temperature": body.get("temperature", 0.2),
                },
            ):
                response = chunk["message"]["content"]
                # print(f"Response: {response}")
                yield response

        except Exception as e:
            yield f"Error: {e}"
