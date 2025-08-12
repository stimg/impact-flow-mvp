# Define variables for LLM
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

category_parameter = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "description": "Category name extracted from user message",
            "enum": [
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
                        - What products do you have in your range?
                        - What products do you have?
                        - What kind of products do you have?                        
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
                        - Which categories do you have?

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
                        - Which products do you have in the Body & Clean category?
                        - Show me the products from the Vitality & Family.
                        - What is in the Omega-Oils category?
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
                        Fetches a list of most suitable products for user request when no particular product is mentioned.
                        Product properties, which must be extracted from the user request:
                        - ingredients
                        - application area
                        - target audience
                        - user experience
                        - recipe origin
                        You **must** extract product property from the user message.
                        You **must** take only one most suitable property from the properties list above.

                        Use it if the query applies to **many** products only.
                        Use it if the 'Ethno Health' string is in the user message.
                        
                        Examples:
                        - Which products are best for the sportsmen?
                        - Which products contain the omega oils?
                        - Which product helps with allergies?
                        - Which products are effective against coughs?
                        - What do you have against coughs?
                        - Do you have products for clarity and concentration?
                        - What do people say about Ethno Health products?
                        - Which products are created in Tibet?
                    """,
            "parameters": {
                "type": "object",
                "properties": {
                    "property": {
                        "type": "string",
                        "description": "Extracted product property",
                        "enum": [
                            "target_audience",
                            "application_area",
                            "ingredients",
                            "formulation_origin",
                            "user_experience",
                        ],
                    },
                    "user_message": {
                        "type": "string",
                        "description": "User message",
                    },
                },
                "required": ["property", "user_message"],
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
                        - What do you know about the Lung product?
                        - What information is there about Brenner?
                        - What is the Omega Go! product?
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
                            - How does essence aminos affect the skin during pregnancy?
                            - Can I consume the product during pregnancy?
                            - Can pregnant women use Ethno Health products?
                            - Can the product be taken while using medication?
                            - May I use the product if I am taking other medications?
                            - Are there any contraindications for taking the product?
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
                        - What do the people say about the product?
                        - Are there any user stories about the product usage and results?
                        - How do the users rate the product?
                        - Do you have any user opinions about the product?
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
                        - What ingredients does the product contain?
                        - What's in it?
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
                        - What is this product for?
                        - Is the product suitable for losing weight?
                        - Can this product improve concentration?
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
                        - How often should I take the product?
                        - How much should I take per day?
                        - Are there any recommended dosages for the product?                    """,
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
                        - Who is the product best suited for?
                        - Which people is it suitable for?
                        - Which target groups is it recommended for?
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
                        - How the product was created?
                        - Who invented the recipe?
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
                        - What is the origin of the product?
                        - Tell me the product history.
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
