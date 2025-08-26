import json
import psycopg2
import re
import time
from typing import Literal

from openai import OpenAI
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel, Field


class Pipe:
    class Valves(BaseModel):
        RAG_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model to use for RAG.",
        )
        TOOLS_MODEL_ID: Literal[
            "qwen/qwen-2.5-7b-instruct",
            "qwen/qwen2.5-7b-instruct",
            "gpt-4.1-nano-2025-04-14",
        ] = Field(
            default="qwen/qwen-2.5-7b-instruct",
            description="Model to use for the tools selection.",
        )
        EMBEDDING_MODEL_ID: str = Field(
            default="bge-m3",
            description="Model to use for embedding generation.",
        )
        PROMPT_LIST: str = Field(
            default="""
                Folgende Punkte immer zu beachten:
                - Eine horizontale Trennlinie (---)
                - Produktname
                - Kategorie
                - Kurzbeschreibung
                - Produktwebseite
                
                Du **musst** das Format exakt einhalten, **ohne Ausnahmen**.  
                Verwende **vor jeder Sektion eine leere Zeile** (also zwei neue Zeilen), genau so wie hier im Beispiel:
                
                ---
                
                **Produktname: Energy-Plus**
                
                *Kategorie: Nahrungsergänzung*
                
                Kurzbeschreibung: Steigert die Energie im Alltag.
                
                Weitere Informationen über das Produkt: [Produktname](<Produktwebseite>)
                
                Antworte nur in diesem Format und **NICHT anders**.
                
                **WICHTIG:**  
                – Immer **eine komplett leere Zeile** direkt *vor* der Zeile mit `---`  
                – `---` **muss allein** in seiner eigenen Zeile stehen  
                – Immer **eine komplett leere Zeile** direkt *nach* `---`, auch wenn es das Ende der Antwort ist            """,
            description="System prompt for product list.",
        )
        PROMPT_DETAILS: str = Field(
            default="""
                Folgende Punkte immer zu beachten:
                - Produktname: zeige vollständige Produktname.
                - Produktkategorie.
                - Produktbeschreibung: Erkläre, was das Produkt ist, welche Hauptmerkmale und Funktionen es hat und welchen Nutzen es den Nutzerinnen bringt.
                - Zielgruppe: Beschreibe, für wen das Produkt besonders geeignet ist und welche spezifischen Bedürfnisse es erfüllt.
                - Anwendung: Erkläre, wie das Produkt anzuwenden ist und welche typischen Anwendungsszenarien es gibt.
                - Vorteile: Hebe die wichtigsten Vorteile hervor, die das Produkt von anderen abheben, und erläutere den Mehrwert für die Nutzerinnen.
                - Produktwebseite.
                - Relevante zur Benutzerfrage Abschnitte.
                - Eine horizontale Trennlinie
                - Einen Hinweis, dass alle Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!
                
                Du **musst** das Format exakt einhalten, **ohne Ausnahmen**.  
                Verwende **vor jeder Sektion eine leere Zeile** (also zwei neue Zeilen), genau so wie hier im Beispiel:
                
                **Produktname: Energy-Plus**
                
                *Kategorie: Nahrungsergänzung*
                
                Produktbeschreibung: Steigert die Energie im Alltag.
                
                Zielgruppe: Late Menschen
                
                Anwendung: Dreimal pro Tag
                
                Vorteile: Günstig und Effektiv
            """,
            description="System prompt for product details.",
        )
        PROMPT_PROPERTY: str = Field(
            default="""
                Folgende Punkte immer zu beachten:
                - Produktname: zeige vollständige Produktname **wenn definiert**
                - Antwort des Assistenten.
                - Produktwebseite
                - Eine horizontale Trennlinie
                - Einen Hinweis, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!
                
                Du **musst** das Format exakt einhalten, **ohne Ausnahmen**. 
                Verwende **vor jeder Sektion eine leere Zeile** (also zwei neue Zeilen), genau so wie hier im Beispiel:
                
                **Produktname: Energy-Plus**
                
                Die tägliche Verzehrempfehlung beträgt 15 g Pulver in 150 ml Wasser gelöst.
            """,
            description="System prompt for product property.",
        )
        PROMPT_QNA: str = Field(
            default="""
                Folgende Punkte immer zu beachten:
                - Antwort des Assistenten.
                - Produktwebseite
                - Eine horizontale Trennlinie
                - Einen Hinweis, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!
                
                Du **musst** das Format exakt einhalten, **ohne Ausnahmen**. 
                Verwende **vor jeder Sektion eine leere Zeile** (also zwei neue Zeilen), genau so wie hier im Beispiel:
                
                Die Produkte von Ethno Health unterstützen die Gesundheit, indem sie sorgfältig ausgewählte Inhaltsstoffe enthalten, die das allgemeine Wohlbefinden fördern, das Immunsystem stärken und die Energiebalance positiv beeinflussen.
            """,
            description="System prompt for product property.",
        )
        PROMPT_FOOTER: str = Field(
            default="""

                Mehr Informationen findest du hier: [Energy-Plus](https://www.ethno-health.com/energy-plus)
                
                ---
                
                *Bitte beachte, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!*
                
                Antworte nur in GENAU diesem Format und **NICHT anders**
                
                **WICHTIG:**  
                - **du muss immer** das Link auf der **Produktwebseite mit Produktname** und dem hint "Mehr Informationen findest du hier:" direkt nach der Prtoduktinformation und vor der horizontale Trennlinie zeigen.
                – Immer **eine komplett leere Zeile** direkt *vor* der Zeile mit `---`.
                – `---` **muss allein** in seiner eigenen Zeile stehen  
                – Immer **eine komplett leere Zeile** direkt *nach* `---`, auch wenn es das Ende der Antwort ist.
                - **du muss immer** den Text *Bitte beachte, dass **alle** Produkte nicht zur Heilung oder Behandlung von Krankheiten dienen!* in kursiv (*italic*) zeigen!
                
            """,
            description="System prompt for template footer.",
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
            default="https://api.novita.ai/v3/openai",
            description="OpenAI API URL.",
        )
        OPENAI_API_KEY: str = Field(
            default="",
            description="OpenAI API key.",
        )
        EMBEDDING_API_BASE_URL: Literal[
            "https://openrouter.ai/api/v1",
            "https://api.novita.ai/v3/openai",
            "https://api.openai.com/v1",
        ] = Field(
            default="https://api.novita.ai/v3/openai",
            description="OpenAI API URL.",
        )
        EMBEDDING_API_KEY: str = Field(
            default="",
            description="Embedding API key.",
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

        self.openai = OpenAI(
            base_url=self.valves.OPENAI_API_BASE_URL,
            api_key=self.valves.OPENAI_API_KEY,
        )

        self.embedding = OpenAI(
            base_url=self.valves.EMBEDDING_API_BASE_URL,
            api_key=self.valves.EMBEDDING_API_KEY,
        )

    context_product = {}

    def get_user_name_from_full_name(self, username: str | None) -> str:
        if not username:
            return ""

        name_regex = r"^(.+?)(?=\s+(?:von(?:\s+(?:der|den|dem))?|van(?:\s+(?:der|den))?|zu|zur|zum|vom|de|del|du)\b|\s+\S+$)"
        match = re.match(name_regex, username or "")
        return match.group(1) if match else ""

    def generate_embedding(self, text):
        response = self.embedding.embeddings.create(
            model=self.valves.EMBEDDING_MODEL_ID,
            input=text,
        )

        print(f"-----> response: {response}")


        embeddings = response["embeddings"]
        vector = embeddings[0] or []
        print(f"Embedding: {vector}")

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
                SELECT product_id,
                       jsonb_object_agg(
                               vmetadata ->> 'section',
                               chunk_text
                       ) AS info
                FROM product_chunks
                WHERE vmetadata ->> 'section' IN ('name', 'categories', 'reference_link')
                GROUP BY product_id \
                """

        results = self.query_db(query)

        return {
            "prompt": """
            Here is the list with the product info.
            
            Instructions:
            - List all the products from the list, keeping the order in the given list.
            - Use Markdown.
            - Render the product link, using the product name and the product website link from the info.
            - **NEVER** render string "Produktname: " in the product name in the link.
            - After the product name, render the em dash (–) surrounded by spaces.
            - After the dash render the categories as *italic* text.
            - Render every list entry exactly like in this example:

            [Burner](https://www.ethno-health.com/artikeldetail/product) – *Body & Clean*

            """,
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
        results = self.query_db(query)
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
                """
                Here is the list with the product info.
                
                **Instructions:**
                - List all the products from the list, keeping the order in the given list.
                - All output must be in **German**.
                - Use Markdown.
                - Never use header format in the output.
                - Product link, using the product name and the product website link from the info.
                - **NEVER** render string "Produktname: " in the product name in the link.
                - After the product name, render the em dash (–) surrounded by spaces.
                - After the dash render the categories as *italic* text.
                - As next: product short description.
                - Always as next: new line, horizontal line (---), new line.
                - Render every list entry exactly like in this example:            

                [Burner](https://www.ethno-health.com/artikeldetail/product) – *Body & Clean*
                
                Mit neun wichtigen essentiellen Aminosäuren. Die essence aminos aus der Clean-Reihe 
                haben eine herausragende Bedeutung für die Muskulatur und als Vorstufe von Enzymen und Hormonen.

                ---
                
                """
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

    def get_products_by_property(self, property: str, objective: str):
        """
        Queries the PostgreSQL database using the optional categories list.
        For example, it searches for all available products in the category or database.
        """

        prop = property if property != "application_area" else "tags"

        vector = self.generate_embedding(objective)

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
                AND abs(embedding <#> '{vector}') > 0.3
                ORDER BY abs(embedding <#> '{vector}') DESC
                LIMIT 3
            )
            AND vmetadata->>'section' IN ('name', 'categories', '{property}', 'reference_link')
            GROUP BY product_id
        """

        results = self.query_db(query)
        # print(f"----> Results: {results}")

        if isinstance(results, str):
            return {"prompt": "", "data": "No products found."}

        return {
            "prompt": (
                """
                Here is the list with the product info.
                Each product has a name, categories, a property, and a product website.
                The following product properties are available:
                - ingredients
                - application area
                - target audience
                - user experience
                - recipe origin
                
                **Instructions:**
                - List all the products from the list, keeping the order in the given list.
                - All output must be in **German**.
                - Use Markdown.
                - Never use header format in the output.
                - Render product list only without additional text or comments.
                - Product link, using the product name and website link from the info.
                - **NEVER** render string "Produktname: " in the product name in the link.
                - After the product name, render the em dash (–) surrounded by spaces.
                - After the dash render the categories as *italic* text.
                - As next: complete product property text.
                - Always as next: new line, horizontal line (---), new line.
                - Render every list entry **exactly** like in this example:            

                [Burner](https://www.ethno-health.com/artikeldetail/product) – *Body & Clean*
                
                Das produkt ist speziell für Sportler entwickelt. Es hilft dabei, die Energie im Alltag 
                zu steigern und den sportlichen Leistungsgrad zu verbessern.
                
                ---
                
                """
                if len(results) > 1
                else f"{self.valves.PROMPT_DETAILS}{self.valves.PROMPT_FOOTER}"
            ),
            "data": [{"Produktinfo": item["info"]} for item in results],
        }

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
        # print(f"-----> product_name param: {product_name}")

        name = product_name or self.context_product.get("name", "")

        # print(f"-----> property: {property}")
        # print(f"-----> context product: {self.context_product}")
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
            WHERE scope = '{topic}'
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

            if message.get("role", "") == "assistant":
                assistant_message = message.get("content", "")
                # print(f"\n-----> Assistant message: {system_message}\n\n")

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
                    #     f"-----> Context product from history: {self.context_product}"
                    # )

            if message.get("role", "") == "user":
                user_message = message.get("content", "")
                user_message = re.sub(r"\s[!?\.]", "", user_message)
                # print(f"-----> User message: {user_message}")

        # Define variables for LLM
        tools = [
            self.get_product_list,
            self.get_category_list,
            self.get_product_details,
            self.get_products_by_category,
            # self.get_products_by_application,
            self.get_products_by_property,
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
            "get_products_by_property": self.get_products_by_property,
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

        objective_parameter = {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Query objective extracted from user message",
                }
            },
            "required": ["objective"],
        }

        category_parameter = {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Category name extracted from user message",
                    "enum": [
                        "Produktübersicht",
                        "Ethno-Rezepturen",
                        "Chinesische Rezepturen",
                        "Tibetische Rezeptur LUNG" "Omega-Öle & Vitalkomplex",
                        "Omega Go!",
                        "Ethno-Hausapotheke",
                        "Vitality & Family",
                        "Beauty & Lifestyle",
                        "Body & Clean",
                        "Bundles",
                        "Shape Weight Management",
                        "Ethno-Testsatz",
                        "Ethno Health Coach",
                        "Für Kinder geeignet",
                        "Ethno-Events",
                    ],
                }
            },
            "required": ["category"],
        }

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
                    
                    Category names which must be extracted from user message:
                        - Ethno-Rezepturen
                        - Chinesische Rezepturen
                        - Tibetische Rezeptur LUNG
                        - Omega-Öle & Vitalkomplex
                        - Omega Go!
                        - Ethno-Hausapotheke
                        - Vitality & Family
                        - Beauty & Lifestyle
                        - Body & Clean
                        - Bundles
                        - Shape Weight Management
                        - Ethno-Testsatz
                        - Ethno Health Coach
                        - Für Kinder geeignet
                        - Ethno-Events

                    You **must** extract the category name from the user message.
                    You **must** take only one most suitable category name from the category names above.

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
                                "description": "Category",
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
                    Fetches a list of most relevant products for user request.
                    Use it when no particular product is mentioned.
                    Use it if the query applies to **many** products only.
                    Use it if the 'Ethno Health' string is in the user message.
                    
                    Product properties, which must be extracted from the user request:
                    - ingredients
                    - application area
                    - target audience
                    - user experience
                    - recipe origin

                    You **must** extract product property from the user message.
                    You **must** take only one most suitable property from the properties list above.
                    You **must** extract the query **objective** from the user message. This must be one, 
                    max two words, indicating the user search subject.
                    You find objectives in the examples in the square brackets.

                    Examples:
                    - Welche Produkte sind am besten für [Sportler]?
                    - Welche Produkte enthalten [Omega-Öle]?
                    - Welches Produkt hilft bei [Allergien]?
                    - Welche Produkte sind wirksam gegen [Husten]?
                    - Was haben Sie gegen [Husten]?
                    - Haben Sie Produkte für Klarheit und [Konzentration]?
                    - Was sagen [Menschen] über Ethno Health Produkte?
                    - Welche Produkte wurden in [Tibet] hergestellt?

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
                            "objective": {
                                "type": "string",
                                "description": "Query objective extracted from user message.",
                            },
                        },
                        "required": ["property", "objective"],
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

                    Examples:
                    – Was wissen Sie über das Lungenprodukt?
                    – Welche Informationen gibt es über Brenner?
                    – Was ist das Omega Go!-Produkt?
                    
                    """,
                    "parameters": product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_disclaimer",
                    "description": """
                    Queries the PostgreSQL Q&A database for the related disclaimer if the user asks questions about pregnancy, medicines, or other stuff, not directly connected to the product properties.

                    Examples:
                    - Wie wirken sich essence aminos auf die Haut während der Schwangerschaft aus?
                    - Kann ich das Produkt während der Schwangerschaft einnehmen?
                    - Können schwangere Frauen Ethno Health-Produkte verwenden?
                    - Kann das Produkt während der Einnahme von Medikamenten eingenommen werden?
                    - Darf ich das Produkt verwenden, wenn ich andere Medikamente einnehme?
                    - Gibt es Kontraindikationen für die Einnahme des Produkts?
                    
                    """,
                    "parameters": user_message_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_general_info",
                    "description": """Queries the PostgreSQL Q&A database for the related information.
                    Use it if the user asks general questions about the **Ethno Health** products, 
                    quality, brand, traditional knowledge, research, nutrition, sustainable nutrition, 
                    vegan products, natural ingredients, immune system support, vitality boost,
                    traditional medicine, modern science, well-being, plant-based nutrients,
                    not directly connected to the product properties.
                    
                    Use it if the 'Ethno Health' string is in the user message,
                    but the question is not about product properties:
                    - ingredients
                    - application area
                    - target audience
                    - user experience
                    - recipe origin
                    
                    Examples:
                    - Ich habe gehört, dass Nahrungsergänzungsmittel manchmal kritisch gesehen werden. Was macht die Produkte von Ethno Health so besonders?
                    - Sind die Produkte von Ethno Health für Vegetarier und Veganer geeignet?
                    - Wie profitieren Vegetarier und Veganer von der umfassenden Produktpalette von Ethno Health?
                    - Wie fördert Ethno Health die Nachhaltigkeit bei der Beschaffung seiner Zutaten?
                    - Welche Qualitätsstandards erfüllt Ethno Health bei der Herstellung seiner Produkte?
                    - Wie unterstützt Ethno Health die Gesundheit?
                    - Wie unterstützt Ethno Health die Nachhaltigkeit bei der Beschaffung seiner Zutaten?
                    
                    """,
                    "parameters": user_message_parameter,
                },
            },
            ### Produkt props
            {
                "type": "function",
                "function": {
                    "name": "get_user_experience",
                    "description": """
                    Queries the PostgreSQL database for the user feedback, usage, and user experience for the product with the given name.
                    Use it when the user asks questions about usage, experience, and stories of the single product usage.
                    Use it if the query applies to a single product only.

                    **DO NOT USE** if the user message contains "Ethno Health".
                    
                    Examples:
                    – Was sagen die Leute über das Produkt?
                    – Gibt es Anwenderberichte zur Anwendung und den Ergebnissen?
                    – Wie bewerten die Nutzer das Produkt?
                    – Gibt es Meinungen von Nutzern zum Produkt?

                    """,
                    "parameters": product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_ingredients",
                    "description": """
                    Queries the PostgreSQL database for the particular product ingredients.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.

                    Examples:
                    - Welche Inhaltsstoffe enthält das Produkt?
                    - Was ist drin?
                    
                    """,
                    "parameters": opt_product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_application_area",
                    "description": """
                    Queries the PostgreSQL database for the particular product application area.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.

                    Examples:
                    - Wie wirkt das produkt?
                    - Wofür ist dieses Produkt geeignet?
                    - Ist das Produkt zum Abnehmen geeignet?
                    - Kann dieses Produkt die Konzentration verbessern?
                    
                    """,
                    "parameters": opt_product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_intake_recommendation",
                    "description": """
                    Queries the PostgreSQL database for the particular product intake recommendations.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.

                    Examples:
                    - Wie oft sollte ich das Produkt einnehmen?
                    - Wie viel sollte ich pro Tag einnehmen?
                    - Gibt es Dosierungsempfehlungen für das Produkt?

                    """,
                    "parameters": opt_product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_target_audience",
                    "description": """
                    Queries the PostgreSQL database for the particular product target people group and matching audience.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.

                    Examples:
                    – Für wen ist das Produkt am besten geeignet?
                    – Für welche Personen ist es geeignet?
                    – Für welche Zielgruppen ist es empfehlenswert?
                    
                    """,
                    "parameters": opt_product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_formulation_origin",
                    "description": """
                    Queries the PostgreSQL database for the particular product recipe or formulation origin.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.

                    Examples:
                    - Wie ist das Produkt entstanden?
                    - Wer hat das Rezept erfunden?
                    
                    """,
                    "parameters": opt_product_name_parameter,
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_product_history",
                    "description": """
                    Queries the PostgreSQL database for the history of the particular product creation, its author, country, circumstances, origin, or invention.
                    **DO NOT** use the tool if the user message contains "Ethno Health" name.
        
                    Examples:
                    - Woher stammt das Produkt?
                    - Erzählen Sie mir die Produktgeschichte.
                    
                    """,
                    "parameters": opt_product_name_parameter,
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
{"name":"get_products_by_property", "arguments":{"property": "user_experience", "user_message": "Do you have success stories for Products?"}}
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
            print(f"Function call result: {result.get('data', '')}")
            print("================================================")

        messages = [
            {
                "role": "system",
                "content": f"""{system_message}\n\n{result.get('prompt', '')}\n\nUsername: {username}\n\nContext:\n\n{result.get('data', '')}\n\n""",
            },
            {
                "role": "user",
                "content": f"/no_think {user_message}",
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
                max_tokens=8192,
                temperature=body.get("temperature", 0),
                top_p=body.get("top_k", 0.9),
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

            end_time = time.perf_counter()
            duration = end_time - start_time
            print("------------------------------------------------")
            print(f"Chat completion processing time: {duration:.1f} seconds")
            print("================================================")

        except Exception as e:
            yield f"Error: {e}"
