import os
import json
import traceback
from openai import OpenAI
from .database import DatabaseManager

class QueryEngine:
    def __init__(self):
        # Initialize Database
        self.db_manager = DatabaseManager()
        
        # --- OpenCode Go API Config ---
        # We check both OPENCODE_API_KEY and OPENCODE_GO_API_KEY for convenience
        self.api_key = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENCODE_GO_API_KEY")
        if not self.api_key:
            raise ValueError("OPENCODE_API_KEY (or OPENCODE_GO_API_KEY) not found in environment variables")
        
        self.base_url = "https://opencode.ai/zen/go/v1"
        self.model = "deepseek-v4-flash"
        
        # Initialize OpenAI client pointed to OpenCode Go endpoint
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )

    def process_query(self, user_query: str) -> str:
        try:
            # Step 1: Translate (with OpenCode Go)
            translation_result = self._execute_opencode(
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
                return "I couldn't find any relevant documents to answer your question."

            # Step 3: Generate Answer (with OpenCode Go)
            final_answer = self._execute_opencode(
                task="generation",
                prompt=user_query, # Use original query in prompt
                context=context_text,
                target_lang=user_lang
            )
            
            if not final_answer:
                return "Sorry, the AI model is currently overloaded. Please try again later."
            
            return final_answer

        except Exception:
            print("CRITICAL ERROR in QueryEngine:")
            traceback.print_exc()
            return "Sorry, something went wrong while processing your query. Please try again later."

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

    def _execute_opencode(self, task, **kwargs):
        """
        Executes a call to OpenCode Go endpoint using deepseek-v4-flash.
        """
        system_instr_trans = """You are a translator.
1. Detect the language of the query.
2. Translate it to English.
3. Return JSON: {"translation": "...", "detected_language": "..."}"""

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

        try:
            print(f"🔄 Querying OpenCode Go ({self.model}) for {task}...")
            
            create_params = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": sys_instr},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.1
            }
            if is_json:
                create_params["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**create_params)
            
            result = response.choices[0].message.content
            
            if result:
                if is_json:
                    # Clean up markdown if present
                    clean = result.replace("```json", "").replace("```", "").strip()
                    return json.loads(clean)
                return result

        except Exception as e:
            print(f"❌ Failed to query OpenCode Go: {e}")
            return None
