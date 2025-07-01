from pydantic import BaseModel, Field
import json, requests
import psycopg2
import numpy as np
import ollama
from psycopg2.extras import RealDictCursor
from langchain.agents import initialize_agent, Tool
from langchain.llms import OpenAI



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

    def call_ollama(self, system_prompt, user_message):
        response = ollama.chat(
            model='phi4-mini',
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        )
        return response['message']['content']

    def agent_loop(self, system_prompt, user_message):
        # 1. Get LLM decision
        llm_response = self.call_ollama(system_prompt, user_message)
        try:
            tool_call = json.loads(llm_response)
            tool = tool_call.get("tool")
            params = tool_call.get("parameters", {})

            if tool == "get_product_list":
                result = self.get_product_list(**params)
            elif tool == "get_product_details":
                result = self.get_product_details(**params)
            else:
                result = "Unknown tool"

            # Optionally, you can ask the LLM to summarize the tool result for the user
            print(f"TOOL RESULT: {result}")
            # For a more agentic loop, send the tool result back as context
            # and continue the conversation if needed

        except Exception as e:
            print("LLM Response (no tool call detected):", llm_response)

    def get_product_list(self, categories: str = None):
        if categories:
            query_vector = self.generate_embedding(categories)
            query = f"""
                SELECT 
                    product_id,
                    embedding, 
                    jsonb_object_agg(
                        vmetadata->>'section',
                        chunk_text
                    ) AS product_info
                FROM product_chunks 
                WHERE section = 'categories' 
                ORDER BY '{query_vector}' <#> embedding 
                GROUP BY product_id
            """
        else:
            query = f"""
                SELECT
                    product_id,
                    jsonb_object_agg(
                            vmetadata->>'section',
                            chunk_text
                    ) AS product_info
                FROM product_chunks
                WHERE vmetadata->>'section' IN ('name', 'categories', 'short_description')
                GROUP BY product_id;
        """

        results = self.query_db(query)
        return [
            {
                "name": item["name"],
                "categories": item["categories"],
                "short_description": item["short_description"],
            } for item in results
        ]

    def get_product_details(self, query):
        """
        Queries the PostgreSQL database using the provided user message.
        For example, it searches for a matching answer in the FAQ table.
        """
        # Convert text to embedding for vector search
        query_vector = self.generate_embedding(query)

        query = f"""
            SELECT 
                product_id,
                jsonb_object_agg(
                    vmetadata->>'section',
                    chunk_text
                ) AS product_info
            FROM product_chunks
            ORDER BY embedding <#> '{[query_vector]}'
            LIMIT 1
        """

        results = self.query_db(query)

        if not results:
            return "No matching product found in the database."

        return [
            {
                "name": item["name"],
                "categories": item["categories"],
                "short_description": item["short_description"],
            } for item in results
        ]

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

        functions = [
            {
                "name": "get_product_list",
                "description": "Fetches a list of products. Use when the user asks about a available products or product categories.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "categories": {"categories": "string", "description": "Comma separated product categories (optional)"}
                    }
                }
            },
            {
                "name": "get_product_details",
                "description": "Fetches detailed information about a product. Use when the user refers to a specific product by name.",
                # Make available if we use selection by ID not the semantic search by section
                # "parameters": {
                #     "type": "object",
                #     "properties": {
                #         "product_id": {"type": "string", "description": "Unique identifier of the product"}
                #     },
                #     "required": ["product_id"]
                # }
            }
        ]

        tools = [
            Tool(
                name="get_product_list",
                func=self.get_product_list_tool,
                description="Fetches products by category."
            ),
            Tool(
                name="get_product_details",
                func=self.get_product_details_tool,
                description="Fetches details for a product by name."
            ),
        ]

        llm = OpenAI(
            model="phi4-mini",
            messages=None,
            tools = functions,
            tool_choice = 'auto',
            temperature = 0.2,
        )

        agent = initialize_agent(tools, llm, agent_type="openai-functions")

    # Get system and user messages
        for message in messages:
            if message.get("role", "") == "system":
                system_message = message.get("content", "")

            if message.get("role", "") == "user":
                user_message = message.get("content", "")

        # Query the PostgreSQL database for a related answer.
        db_result = self.query_database(user_message)
        print(f"DB result: {db_result}")

        # Construct a prompt that includes both the user's request and the database query result.
        prompt = (
            f"QUERY: {user_message}\n"
            f"CONTEXT: {db_result}\n\n"
            f"{self.valves.PROMPT}"
        )
        print(f"System message: {system_message}")
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
