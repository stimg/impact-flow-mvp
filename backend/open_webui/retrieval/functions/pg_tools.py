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
        PROMPT: str = Field(
            default="Basierend auf den obigen Informationen generiere eine abschließende Antwort.",
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

    def __init__(self):
        self.valves = self.Valves()

    def is_normalized(vec, tol=1e-6):
        norm = np.linalg.norm(vec)
        return abs(norm - 1.0) < tol

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

        # print(f"Embedding is normalized: {self.is_normalized(vector)}")

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
                GROUP BY product_id; \
                """

        results = self.query_db(query)

        return [
            {
                "Product ID": item["product_id"],
                "Produktinformation": item["product_info"],
            }
            for item in results
        ]

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
        return [
            {
                "Product ID": item["product_id"],
                "Produktinformation": item["product_info"],
            }
            for item in results
        ]

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
        print(f"Results: {results}")

        if not results:
            return "No matching product found in the database."

        product_info = results[0]["product_info"]
        product_id = results[0]["product_id"]

        print(f"Produkt details: {product_info}")
        return {
            "Product ID": product_id,
            "Produktinformation": product_info,
        }

    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for a related answer,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")

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

        system_with_tools = (
                "You are a product assistant.\n\n"
                + "You have access to the following tools:\n"
                + f"<|tool|>{tools_schema}</|tool|>\n\n"
                + "Answer directly if you can do so.\n"
                + "When needed, call one of the tools.\n\n"
                + "Examples:\n"
                + "User: Welche Produkte hast du im Sortiment hier?\n"
                + 'Assistant: {"function": "get_product_list", "parameters": {}}\n\n'
                + "User: Welche Produkte in der Kategorie Body & Clean hast du?\n"
                + 'Assistant: {"function": "get_product_list", "parameters": {"category": "Body & Clean"}}\n\n'
                + "User: Was weisst du über das Lung Produkt?\n"
                + 'Assistant: {"function": "get_product_details", "parameters": {"name": "Lung"}}\n\n'
        )

        ollama = Client(
            host="http://localhost:11434", headers={"Authorization": "Bearer ollama"}
        )

        response = ollama.chat(
            model="phi4-mini",
            messages=[
                {"role": "system", "content": system_with_tools},
                {"role": "user", "content": user_message},
            ],
            tools=tools,
            format="json",
        )

        print(f"Chat Completion response: {response}")

        content = json.loads(response["message"]["content"])
        # print(f"Content: {content}")

        if content:
            name = content["function"]
            parameters = content["parameters"]

            print(f"Function: {name}")
            print(f"Parameters: {parameters}")

            db_result = handlers[name](**parameters)

        else:
            db_result = "No handler defined for this tool call."

        print(f"DB result: {db_result}")

        # Construct a prompt that includes both the user's request and the database query result.
        prompt = (
            f"QUERY: {user_message}\n"
            f"CONTEXT: {db_result}\n\n"
            f"{self.valves.PROMPT}"
        )
        # print(f"System message: {system_message}")
        # print(f"Prompt: {prompt}")

        del body["messages"]

        # Retrieve the model id from the provided model string.
        # Update the payload for the API call.
        payload = {
            **body,
            "model": self.valves.MODEL_ID,
            "prompt": prompt,
            "system": system_message,
            "format": "",
            "options": {
                "num_ctx": 8196,
                "top_k": 5,
                "top_p": 0.5,
                "max_tokens": 2048,
                "temperature": 0.7,
            },
        }
        # print(f"payload: {payload}")

        headers = {
            "Content-Type": "application/json",
        }
        try:
            with requests.post(
                    url=f"{self.valves.API_BASE_URL}/generate",
                    json=payload,
                    headers=headers,
                    stream=body.get("stream", False),
                    timeout=30,
            ) as r:
                r.raise_for_status()
                for raw_line in r.iter_lines(decode_unicode=True):
                    if not raw_line:
                        continue

                    d = json.loads(raw_line)
                    response = d.get("response", "")
                    print(f"Response: {d.get('response', '')}")
                    yield response

                    if d["done"]:
                        break

        except Exception as e:
            return f"Error: {e}"
