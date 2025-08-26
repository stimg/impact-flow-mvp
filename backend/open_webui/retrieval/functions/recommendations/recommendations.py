import json
import re
import time
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field


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
            default="""

            INSTRUCTIONS:
            - You **must** replace "Username" with the user name taken from the Username.
            - You **must** render everything in Markdown format, **NO HTML, no additional quotemarks!**
            - You must always create the following sections using the JSON object from the Context:
              1. Tags
              2. Relevanz
              2. Empfohlene Produkte
              3. Weitere Empfehlungen
              4. Anwendungsbereich
            
            - Take "Tags" from the "tags" JSON field. Always render them in cursive (*italic*).
            - Take "Relevanz" from the "score" JSON field.
            - Take "Empfohlene Produkte" from the "recommended" JSON field.
            - Take "Weitere Empfehlungen" from the "suitable" JSON field.
            - Take "Anwendungsbereich" from the "info" JSON field. Use this field to create a full relevant answer.

            - Render every section as a separate paragraph with the section name in bold (**Tags:**).
            - Always render "Tags" section content in *italic*
            - Always render the content of these sections as text, **no lists or bullet points**!

            - For the sections "Empfohlene Produkte", "Weitere Empfehlungen":
              1. Always render every product name as the product link.
              2. Take every product name and find its link by product name in the JSON "links" object.

            """,
            description="Instruction how render content.",
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

    context_product = {}

    def __init__(self):
        self.valves = self.Valves()

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

    ### --- PIPE functon ---
    def pipe(self, body: dict, __user__: dict):
        """
        Uses the provided body to query the PostgreSQL database and then call the Chat Completion endpoint.
        This method extracts the user's request from the messages, queries PostgreSQL for related recommendations,
        constructs a prompt including the database result, and then sends the prompt to the API.
        """
        print(f"pipe: {__name__}")
        # print(f"\nBody: {body}\n")

        openai = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

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

        response = openai.chat.completions.create(
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
                Context:\n\n{result}
                {system_message}
                {self.valves.PROMPT if result else f"{self.valves.PROMPT_NOTHING_FOUND}"}
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
