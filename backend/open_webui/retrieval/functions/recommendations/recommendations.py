import json
import psycopg2
import re
import requests
import time
import numpy as np
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

from open_webui.retrieval.functions.data import recommendation_tags


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

        PROMPT: str = Field(
            default="""

            INSTRUCTIONS:
            - You **must** replace "Username" with the user name taken from the Username.
            - - **Headings and other separated formats are forbidden.**
            - You **must** render everything in Markdown format, **NO HTML, no additional quotemarks!**
            - You must always create the following sections using the JSON object from the Context:
              1. Tags
              2. Relevanz
              3. Empfohlene Produkte
              4. Weitere Empfehlungen
              5. Anwendungsbereich
              6. New section with "---"
              7. Mentora Pro Tipp (can be empty)
            
            - Take "Tags" from the "tags" JSON field. Always render them in cursive (*italic*).
            - Take "Relevanz" from the "score" JSON field. Always convert it to a percent.
            - Take "Empfohlene Produkte" from the "recommended" JSON field.
            - Take "Weitere Empfehlungen" from the "suitable" JSON field.
            - Take "Anwendungsbereich" from the "info" JSON field. Use this field to create a full relevant answer.
            - You must always take "Mentora Pro Tipp" from the "hint" JSON field. DO NOT invent, alter, assume, or extend beyond the context. If the context does not contain a hint, explicitly state: "kein Tipp".

            - Render every section as a separate paragraph with the section name in bold (**Tags:**).
            - Always render "Tags" section content in *italic*
            - Always render the content of these sections as text, **no lists or bullet points**!

            - For the sections "Empfohlene Produkte", "Weitere Empfehlungen":
              1. You must render every product name as the product link.
              2. You must take every product name and find its link by product name in the JSON "links" object.
              3. Altering or changing the product name or link is strictly forbidden.

            - For the "Mentora Pro Tipp" section:
              1. Render "Mentora Pro Tipp 💡:" section name before the content.
              3. NEVER render a product link in this section.

            """,
            description="Instructions on how to render content.",
        )
        PROMPT_NOTHING_FOUND: str = Field(
            default="""

            INSTRUCTIONS:
            - **DO NOT** invent answer!
            - **DO NOT** give ANY recommendations even if you very want to do this!!!
            - Politely say we've found nothing for your request.
            - Ask to refine the query.
            
            """,
            description="Instruction what to say if nothing found.",
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

    context_product = {}

    def __init__(self):
        self.valves = self.Valves()

        self.query_db = partial(query_db, self)
        self.get_user_name_from_full_name = partial(get_user_name_from_full_name, self)
        self.get_embedding = partial(get_embedding, self)
        self.sanitize_user_input = partial(sanitize_user_input, self)

    def get_recommendation(self, tags, user_message=""):
        """Queries the PostgreSQL Q&A database for the given tag(s)"""

        # print(
        # f"--------> User message: {sanitize_user_input(user_message) or 'EMPTY_QUERY_SENTINEL'}"
        # )
        # print(f"---> tags: {tags}")
        vec_query = (
            # Make a fallback for the empty user message
            self.get_embedding(
                sanitize_user_input(user_message)
                if user_message
                else "EMPTY_QUERY_SENTINEL"
            )
        )

        # Get recommendation
        sql = """
            SET hnsw.ef_search = 40;
            
            WITH
            q AS (
              SELECT
                %s::vector AS qvec,
                websearch_to_tsquery('german', %s) AS qtext,
                normalize_csv(%s) AS qtags
            ),
            
            -- 1) Exact tag short-circuit
            exact_tag AS (
              SELECT p.id, 1.0 AS score
              FROM product_recommendations p, q
              WHERE p.tags_arr && q.qtags
            ),
            has_exact AS (
              SELECT EXISTS(SELECT 1 FROM exact_tag) AS found
            ),
            
            -- 2) Score all rows
            scored_all AS (
              SELECT
                p.id,
                COALESCE(1 - (p.vec_info <=> (SELECT qvec FROM q)), 0) AS s_info_dense,
                ts_rank_cd(p.info_tsv, (SELECT qtext FROM q))           AS s_info_bm25,
                (
                  SELECT MAX(similarity(t, qt))
                  FROM unnest(p.tags_arr) t
                  CROSS JOIN LATERAL unnest((SELECT qtags FROM q)) qt
                )                                                       AS s_tags_trgm
              FROM product_recommendations p
            ),
            
            -- 3) Normalize (NULL-safe for channels that might be missing)
            norm AS (
              SELECT
                id,
                COALESCE(
                  (s_info_dense - MIN(s_info_dense) OVER())
                  / NULLIF(MAX(s_info_dense) OVER() - MIN(s_info_dense) OVER(), 0), 0
                ) AS n_info_dense,
                COALESCE(
                  (s_info_bm25 - MIN(s_info_bm25) OVER())
                  / NULLIF(MAX(s_info_bm25) OVER() - MIN(s_info_bm25) OVER(), 0), 0
                ) AS n_info_bm25,
                COALESCE(
                  (s_tags_trgm - MIN(s_tags_trgm) OVER())
                  / NULLIF(MAX(s_tags_trgm) OVER() - MIN(s_tags_trgm) OVER(), 0), 0
                ) AS n_tags_trgm
              FROM scored_all
            ),
            
            -- 4) Weighted hybrid
            hybrid AS (
              SELECT id, 0.5*n_info_dense + 0.35*n_info_bm25 + 0.15*n_tags_trgm AS score
              FROM norm
            ),
            
            -- 5) Final selection
            final_ids AS (
              SELECT id, score FROM exact_tag
              UNION ALL
              SELECT h.id, h.score
              FROM hybrid h, has_exact hx
              WHERE NOT hx.found
                AND h.score >= 0.9
            )
            SELECT p.id, p.tags, p.recommended, p.suitable, p.info, f.score
            FROM final_ids f
            JOIN product_recommendations p ON p.id = f.id
            WHERE f.score > 0.8
            ORDER BY f.score DESC
            LIMIT 1;
        """
        result = self.query_db(sql, "one", (vec_query, user_message, tags))

        # Get product links for recommended products
        sql = """
              SELECT jsonb_object_agg(
                             regexp_replace(pc.vmetadata->>'name', '^\\s*Produktname:\\s*', ''),
                             regexp_replace(pc.chunk_text, '^\\s*Produk(t?)webseite:\\s*', '')
                     ) AS links
              FROM product_chunks pc
              WHERE pc.section = 'reference_link'
                AND EXISTS (
                  SELECT 1
                  FROM unnest(normalize_csv(%s)) AS pat
                  WHERE lower(regexp_replace(pc.vmetadata->>'name', '^\s*Produktname:\s*', '')) ILIKE pat || '%%'
              ) \
              """

        if not result:
            return None

        res = self.query_db(
            sql, "one", (f"{result['recommended']}, {result['suitable']}",)
        )
        links = res["links"] if res else None
        # info = res["info"] if res else None

        # print(f"-----> Info: {info}")
        # print(f"-----> Links: {links}")
        # print(f"-----> Result: {res}")

        return {**result, "links": links}

    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "get_recommendation",
                "description": f"""
                Fetches a list of the most relevant recommendations for given tags.
                
                Tag list: {', '.join(recommendation_tags)}

                You **must** extract the tags from the user message. These must be one 
                or two most related words, indicating the user's ailment, illness, diagnosis, or health complaint.
                You find tags in the examples in the square brackets.
                You **must** take one or two most related tags from the tag list above.

                Examples:
                - Was könnt ihr gegen [Ängste] empfehlen?
                - Welche Produkte helfen bei [Allergie]?
                - Ich habe Probleme mit [Augen].

                """,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "string",
                            "description": "The tag from the list extracted from the user message",
                            "enum": recommendation_tags,
                        },
                        "user_message": {
                            "type": "string",
                            "description": "User message",
                        },
                    },
                    "required": ["tags"],
                },
            },
        },
    ]

    system_prompt_tools = (
            """
            You are the Ethon Health product assistant.
            You recommend the products based on the user's request.
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
        {"name":"get_recommendations", "arguments":{"tags": "Angstzustände, Angst", "user_message": "Welche Produkte helfen bei Allergie?"}}
        
        Begin your response now in this JSON-only format.

        """
    )

    ### --- PIPE funciton ---
    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for related recommendations,
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
            if message.get("role", "") == "system":
                system_message = message.get("content", "")
                # print(f"\n-----> System message: {system_message}\n\n")

            if message.get("role", "") == "user":
                user_message = message.get("content", "")
                user_message = re.sub(r"\s[!?\.]", "", user_message)
                # print(f"-----> User message: {user_message}")

        messages = [
            {
                "role": "system",
                "content": self.system_prompt_tools,
            },
            {
                "role": "user",
                "content": user_message,
            },
        ]

        start_time = time.perf_counter()

        response = self.openai.chat.completions.create(
            model=self.valves.TOOLS_MODEL_ID,
            messages=messages,
            stream=False,
            temperature=0,
        )

        # print(f"-----> response: {response}")
        duration = time.perf_counter() - start_time

        print("================================================")
        print("------------ Tool search query -----------------")
        print(f"- User: {__user__['name']}")
        print(f"- Model: {response.model}")
        print("------------------------------------------------")

        ### Statistic
        if hasattr(response, "total_duration"):
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

        if not function_name:
            print(f"No valid function call. Exit.")
            return None

        db_query_start = time.perf_counter()
        result = self.get_recommendation(**arguments)
        end_time = time.perf_counter()

        print(f"- Function name: {function_name}")
        print(f"- Arguments: {arguments}")
        print(f"- User message: {user_message}")
        print("================================================")
        print(f"Tool search time: {duration:.1f} s")
        print(f"DB query duration: {end_time - db_query_start:.1f} s")
        print(f"Total tool time: {end_time - start_time:.1f} s")
        print("================================================")

        if result:
            print(f"Function call result: {result}")
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
                Context:\n\n{result}\n\n
                {system_message}\n\n
                {self.valves.PROMPT if result else f"{self.valves.PROMPT_NOTHING_FOUND}"}\n\n
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

            for chunk in self.openai.chat.completions.create(
                    model=self.valves.RAG_MODEL_ID,
                    messages=messages,
                    stream=True,
                    temperature=body.get("temterature", 0),
                    top_p=body.get("top_p", 0.1),
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

            # yield f"\n\n---\n\n**Antwort aus der DB:**\n\n{result}"

            end_time = time.perf_counter()
            duration = end_time - start_time
            print("================================================")
            print(f"Chat completion processing time: {duration:.1f} seconds")
            print("================================================")

        except Exception as e:
            yield f"Error: {e}"
