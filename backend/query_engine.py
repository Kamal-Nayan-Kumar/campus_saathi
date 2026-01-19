from google import genai
from google.genai import types
import os
import json
import traceback
import requests
from azure.ai.inference import ChatCompletionsClient
from azure.core.credentials import AzureKeyCredential
from .database import DatabaseManager

class QueryEngine:
    def __init__(self):
        # Initialize Database
        self.db_manager = DatabaseManager()
        
        # --- API Keys ---
        self.keys = {
            "gemini": os.getenv("GEMINI_API_KEY"),
            "groq": os.getenv("GROQ_API_KEY"),
            "cerebras": os.getenv("CEREBRAS_API_KEY"),
            "github": os.getenv("GITHUB_TOKEN"),
            "perplexity": os.getenv("PERPLEXITY_API_KEY")
        }

        # Initialize Gemini Client if key exists
        if self.keys["gemini"]:
            self.gemini_client = genai.Client(api_key=self.keys["gemini"])

        # Initialize GitHub Client if key exists
        if self.keys["github"]:
            self.github_client = ChatCompletionsClient(
                endpoint="https://models.inference.ai.azure.com",
                credential=AzureKeyCredential(self.keys["github"]),
            )

        # --- Rotation Order ---
        # Each entry: (Provider, ModelName)
        self.model_rotation = [
            ("gemini", "gemini-2.5-flash-lite"), # 1. Primary (Fast)
            ("gemini", "gemini-1.5-flash"),      # 2. High Quota
            ("groq", "llama-3.1-8b-instant"),    # 3. Fast Inference
            ("cerebras", "llama3.1-8b"),         # 4. Super Fast
            ("github", "Meta-Llama-3.1-8B-Instruct"), # 5. GitHub Models
            ("perplexity", "sonar-pro")          # 6. Final Backup
        ]

    def process_query(self, user_query: str) -> str:
        try:
            # Step 1: Translate (with Rotation)
            translation_result = self._execute_with_rotation(
                task="translation", 
                prompt=user_query
            )
            
            # If translation failed completely, fallback to original
            if not translation_result:
                english_query = user_query
                user_lang = "English"
            else:
                english_query = translation_result.get("translation", user_query)
                user_lang = translation_result.get("detected_language", "English")
            
            print(f"Debug: Original: {user_query}, Translated: {english_query}, Lang: {user_lang}")

            # Step 2: Retrieve Context
            safe_query = english_query[:1000]
            context_text = self._retrieve_context(safe_query)

            if not context_text:
                return "I couldn't find any relevant documents to answer your question." if user_lang == "English" else "Mujhe koi relevant documents nahi mile."

            # Step 3: Generate Answer (with Rotation)
            final_answer = self._execute_with_rotation(
                task="generation",
                prompt=user_query, # Use original query in prompt
                context=context_text,
                target_lang=user_lang
            )
            
            if not final_answer:
                return "Sorry, all my AI brains are currently overloaded. Please try again later."
            
            return final_answer

        except Exception as e:
            print(f"CRITICAL ERROR in QueryEngine: {str(e)}")
            traceback.print_exc()
            raise e

    def _retrieve_context(self, query: str) -> str:
        try:
            collection = self.db_manager.get_collection()
            results = collection.find(
                sort={"$vectorize": query},
                limit=5,
                projection={"content": 1}
            )
            documents = []
            for doc in results:
                if 'content' in doc:
                    documents.append(doc['content'])
            return "\n\n".join(documents)
        except Exception as e:
            print(f"Search error in Astra DB: {e}")
            return ""

    def _execute_with_rotation(self, task, **kwargs):
        """
        Tries providers in order. Returns result on first success.
        """

        system_instr_trans = """You are a translator.
1. Detect the language of the query.
2. Translate it to English.
3. Return JSON: {\"translation\": \"...\", \"detected_language\": \"...\"}"""

        system_instr_gen = f"""You are a helpful assistant for a college.
Answer the user's question based strictly on the provided context.
Respond in the user's detected language: {kwargs.get('target_lang', 'English')}.
If the info is missing, say so politely in {kwargs.get('target_lang', 'English')}."""

        # Prepare Inputs based on Task
        if task == "translation":
            sys_instr = system_instr_trans
            user_content = kwargs['prompt']
            is_json = True
        else: # generation
            sys_instr = system_instr_gen
            user_content = f"Context:\n{kwargs.get('context')}\n\nUser Question: {kwargs.get('prompt')}\n\nAnswer:"
            is_json = False

        # --- ROTATION LOOP ---
        for provider, model in self.model_rotation:
            if not self.keys.get(provider):
                continue # Skip if no key

            print(f"🔄 Trying {provider} ({model})...")
            
            try:
                result = None
                
                # --- GEMINI ---
                if provider == "gemini":
                    config = {"system_instruction": sys_instr}
                    if is_json: config["response_mime_type"] = "application/json"
                    response = self.gemini_client.models.generate_content(
                        model=model,
                        contents=[user_content],
                        config=types.GenerateContentConfig(**config)
                    )
                    result = response.text

                # --- GROQ ---
                elif provider == "groq":
                    result = self._call_openai_compatible(
                        "https://api.groq.com/openai/v1/chat/completions",
                        self.keys['groq'], model, sys_instr, user_content, is_json
                    )

                # --- CEREBRAS ---
                elif provider == "cerebras":
                    result = self._call_openai_compatible(
                        "https://api.cerebras.ai/v1/chat/completions",
                        self.keys['cerebras'], model, sys_instr, user_content, is_json
                    )

                # --- GITHUB MODELS ---
                elif provider == "github":
                     # Azure SDK logic
                    msgs = [
                        {"role": "system", "content": sys_instr},
                        {"role": "user", "content": user_content}
                    ]
                    # Note: Azure SDK doesn't always support JSON mode flag easily for all models, 
                    # so we rely on prompt engineering (which is already in sys_instr)
                    response = self.github_client.complete(
                        messages=msgs,
                        model=model,
                        temperature=0.1
                    )
                    result = response.choices[0].message.content

                # --- PERPLEXITY ---
                elif provider == "perplexity":
                    result = self._call_openai_compatible(
                        "https://api.perplexity.ai/chat/completions",
                        self.keys['perplexity'], model, sys_instr, user_content, is_json
                    )

                # --- POST-PROCESSING ---
                if result:
                    if is_json:
                        # Clean up markdown if present
                        clean = result.replace("```json", "").replace("```", "").strip()
                        return json.loads(clean)
                    return result

            except Exception as e:
                print(f"❌ Failed on {provider} ({model}): {e}")
                continue # Try next provider

        print("❌ All providers failed.")
        return None

    def _call_openai_compatible(self, url, key, model, sys, user, is_json):
        """Helper for Groq, Cerebras, Perplexity"""
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys},
                {"role": "user", "content": user}
            ]
        }
        if is_json:
            payload["response_format"] = {"type": "json_object"}
            
        response = requests.post(url, json=payload, headers=headers)
        if not response.ok:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
        
        return response.json()['choices'][0]['message']['content']
