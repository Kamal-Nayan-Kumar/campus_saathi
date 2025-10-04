from google import genai
from google.genai import types
import os
import json
from typing import Dict

class QueryEngine:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=api_key)
        
    def translate_and_classify(self, user_query: str) -> Dict:
        """
        Step 5: Translation and Intent Recognition using Gemini 2.5 Flash
        """
        system_instruction = """You are a query translator and intent classifier.

Task:
1. Translate the query to English (if not already in English)
2. Detect the original language of the user's query (e.g., Hindi, English, Hinglish, Telugu, Kannada, etc.)
3. Determine the intent from: mess query, fee query, time table query, bus time table query, canteen, academic
4. Provide a confidence score (0-1)

Output ONLY valid JSON in this format:
{
    "translation": "translated query in English",
    "detected_language": "original language of user query",
    "intent": "one of the intents",
    "confidence_score": 0.95
}"""
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[f"User Query: {user_query}"],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.1
            )
        )
        
        result_text = response.text.strip()
        if result_text.startswith("```"):
            result_text = result_text[7:-3].strip()
        elif result_text.startswith("```"):
            result_text = result_text[3:-3].strip()
            
        return json.loads(result_text)
    
    def generate_answer(self, user_query: str, context_chunks: list, target_language: str = "English") -> str:
        """
        Step 6: Context Augmentation and Final Generation
        """
        context = "\n\n".join([f"Context {i+1}:\n{chunk}" for i, chunk in enumerate(context_chunks)])
        
        system_instruction = f"""You are a helpful college information assistant.

Rules:
1. Answer ONLY using the provided context
2. If the answer is not in the context, say "I don't have information about this in the documents"
3. Be accurate and conversational
4. Provide your answer in {target_language}"""
        
        prompt = f"""Context:
{context}

User Question: {user_query}

Provide a clear answer based only on the context above."""
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.3
            )
        )
        
        return response.text