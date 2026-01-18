from google import genai
from google.genai import types
import os
import json
import traceback
from .database import DatabaseManager

class QueryEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        
        self.client = genai.Client(api_key=api_key)
        self.db_manager = DatabaseManager()

    def process_query(self, user_query: str) -> str:
        try:
            # Step 1: Translate and Detect Language
            translation_result = self._translate_query(user_query)
            english_query = translation_result.get("translation", user_query)
            user_lang = translation_result.get("detected_language", "English")
            
            print(f"Debug: Original: {user_query}, Translated: {english_query}, Lang: {user_lang}")

            # Step 2: Retrieve Context from Astra DB
            # Safety: Truncate query to prevent embedding limit errors (NVIDIA limit is 512 tokens)
            # 2000 chars is roughly 500 tokens. Let's be safe with 1000 chars (~250 tokens).
            safe_query = english_query[:1000]
            
            context_text = self._retrieve_context(safe_query)

            if not context_text:
                return "I couldn't find any relevant documents to answer your question." if user_lang == "English" else "Mujhe koi relevant documents nahi mile."

            # Step 3: Generate Final Answer in Native Language
            return self._generate_final_answer(user_query, context_text, user_lang)

        except Exception as e:
            print(f"CRITICAL ERROR in QueryEngine: {str(e)}")
            traceback.print_exc()
            raise e

    def _retrieve_context(self, query: str) -> str:
        try:
            collection = self.db_manager.get_collection()
            
            # Perform vector search using server-side vectorization
            # sort={"$":"vectorize": query} performs the similarity search
            results = collection.find(
                sort={"$":"vectorize": query},
                limit=5,
                projection={"content": 1}
            )
            
            # Extract content from results
            documents = []
            for doc in results:
                if 'content' in doc:
                    documents.append(doc['content'])
            
            if not documents:
                print("Warning: Astra DB returned 0 results.")
            
            return "\n\n".join(documents)
            
        except Exception as e:
            print(f"Search error in Astra DB: {e}")
            # Don't crash here, just return empty context
            return ""

    def _translate_query(self, query: str) -> dict:
        system_instr = """You are a translator.
1. Detect the language of the query.
2. Translate it to English.
3. Return JSON: {\"translation\": \"...\", \"detected_language\": \"...\"}"""
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[query],
                config=types.GenerateContentConfig(
                    system_instruction=system_instr,
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            print(f"Translation error: {e}")
            return {"translation": query, "detected_language": "English"}

    def _generate_final_answer(self, original_query: str, context: str, target_lang: str) -> str:
        system_instr = f"""You are a helpful assistant for a college.
Answer the user's question based strictly on the provided context.
Respond in the user's detected language: {target_lang}.
If the info is missing, say so politely in {target_lang}."""

        prompt = f"""Context:
{context}

User Question: {original_query}

Answer:"""

        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_instr
            )
        )
        return response.text
