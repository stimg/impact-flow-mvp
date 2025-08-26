from pydantic import BaseModel, Field
import json, requests, re, time, psycopg2
import numpy as np
from ollama import Client
from psycopg2.extras import RealDictCursor
from openai import OpenAI
from typing import Literal


class Pipe:
    class Valves(BaseModel):
        RAG_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "mistralai/mistral-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model to use for RAG.",
        )
        TOOLS_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "mistralai/mistral-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model to use for the tools selection.",
        )
        EMBEDDING_MODEL_ID: str = Field(
            default="bge-m3",
            description="Model to use for embedding generation.",
        )
        PROMPT: str = Field(
            default="",
            description="System prompt for answer.",
        )
        TEMPLATE_FOOTER: str = Field(
            default="\n\n---\n\n*Bitte beachte, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!*\n\n",
            description="Footer template (disclaimer).",
        )
        API_BASE_URL: str = Field(
            default="http://localhost:11434/api",
            description="Base URL for accessing Ollama API endpoints.",
        )
        API_BASE_URL: Literal["http://localhost:11434/api",] = Field(
            default="http://localhost:11434/api",
            description="Base URL for accessing Ollama API endpoints.",
        )
        OPENAI_API_BASE_URL: Literal[
            "https://openrouter.ai/api/v1",
            "https://api.novita.ai/v3/openai",
            "https://api.openai.com/v1",
        ] = Field(
            default="https://openrouter.ai/api/v1",
            description="OpenAI API URL.",
        )
        OPENAI_API_KEY: str = Field(
            default="",
            description="OpenAI API key.",
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

    ollama = Client(
        host="http://localhost:11434",
        headers={"Content-Type": "application/json", "Authorization": "Bearer ollama"},
    )

    context_product = {}

    def __init__(self):
        self.valves = self.Valves()

    def get_user_name_from_full_name(self, username: str | None) -> str:
        if not username:
            return ""

        name_regex = r"^(.+?)(?=\s+(?:von(?:\s+(?:der|den|dem))?|van(?:\s+(?:der|den))?|zu|zur|zum|vom|de|del|du)\b|\s+\S+$)"
        match = re.match(name_regex, username or "")
        return match.group(1) if match else ""

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
            result = cur.fetchone()
            cur.close()
            conn.close()

            if not result:
                return "No matching product found in the database."

            return result

        except Exception as e:
            return f"Database error: {e}"

    def get_qna_answer(self, user_message):
        """Queries the PostgreSQL Q&A database for the related answer"""

        if not user_message:
            return {"prompt": "", "data": "User message is not defined"}

        # print(f"--------> User message: {user_message}")
        query_vector = self.generate_embedding(user_message)

        query = f"""
            SELECT answer_text
            FROM q_and_a
            -- WHERE scope = 'qna'
            ORDER BY q_embedding <#> '{query_vector}'
            LIMIT 1
        """
        result = self.query_db(query)
        # print(f"-----> Result: {result}")

        return result["answer_text"]

    ### --- PIPE funciton ---
    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for a related answer,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")
        # print(f"\nBody: {body}\n")

        username = self.get_user_name_from_full_name(__user__["name"])

        # Extract the product from the last message.
        messages = body.get("messages", [])
        # print(f"\nMessages: {messages}\n")

        if not messages:
            return "No messages provided in the request body."

        for message in messages:
            if message.get("role", "") == "system":
                system_message = message.get("content", "")
                # print(f"\n-----> System message: {system_message}\n\n")

            if message.get("role", "") == "assistant":
                assistant_message = message.get("content", "")
                # print(f"\n-----> Assistant message: {system_message}\n\n")

            if message.get("role", "") == "user":
                user_message = message.get("content", "")
                user_message = re.sub(r"\s[!?\.]", "", user_message)
                # print(f"-----> User message: {user_message}")

        start_time = time.perf_counter()

        answer = self.get_qna_answer(user_message)

        print("-------------------")
        print(f"Found answer: {answer}")
        print("-------------------")

        end_time = time.perf_counter()
        duration = end_time - start_time
        print("================================================")
        print(f"Q&A query processing time: {duration:.1f} seconds")
        print("================================================")

        openai = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

        messages = [
            {
                "role": "system",
                "content": f"""
                Username: {username}
                Context:\n\n{answer}
                {system_message}
                """,
            },
            {
                "role": "user",
                "content": f"{user_message}",
            },
        ]

        # print(f"\nMessages: {messages}\n")

        try:
            start_time = time.perf_counter()
            first_chunk = True

            for chunk in openai.chat.completions.create(
                    model=self.valves.RAG_MODEL_ID,
                    messages=messages,
                    stream=True,
                    temperature=1,
            ):
                # print(f"---> chunk: {chunk}")
                if first_chunk:
                    end_time = time.perf_counter()
                    duration = end_time - start_time
                    print("================================================")
                    print(f"Time to first token: {duration:.1f} seconds")
                    print("================================================")
                    first_chunk = False

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

            yield self.valves.TEMPLATE_FOOTER

            yield f"\n\n---\n\n**Antwort aus der DB:**\n\n{answer}"

            end_time = time.perf_counter()
            duration = end_time - start_time
            print("================================================")
            print(f"Chat completion processing time: {duration:.1f} seconds")
            print("================================================")

        except Exception as e:
            yield f"Error: {e}"
