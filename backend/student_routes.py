from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.query_engine import QueryEngine
from backend.vector_store import VectorStoreManager

router = APIRouter()

query_engine = QueryEngine()
vector_store = VectorStoreManager()

class QueryRequest(BaseModel):
    query: str

@router.post("/query")
async def query_documents(request: QueryRequest):
    """
    Student queries the system
    Steps 5-6: Translation, Retrieval, Generation
    """
    try:
        # Step 5: Translate and classify
        translation_result = query_engine.translate_and_classify(request.query)
        
        translated_query = translation_result["translation"]
        detected_language = translation_result["detected_language"]
        
        # Retrieve relevant chunks
        relevant_chunks = vector_store.retrieve_relevant_chunks(translated_query, top_k=5)
        
        if not relevant_chunks:
            return {
                "query": request.query,
                "translation": translated_query,
                "detected_language": detected_language,
                "intent": translation_result["intent"],
                "confidence": translation_result["confidence_score"],
                "answer": "No relevant information found in the documents."
            }
        
        # Step 6: Generate answer in detected language
        answer = query_engine.generate_answer(
            user_query=translated_query,
            context_chunks=relevant_chunks,
            target_language=detected_language
        )
        
        return {
            "query": request.query,
            "translation": translated_query,
            "detected_language": detected_language,
            "intent": translation_result["intent"],
            "confidence": translation_result["confidence_score"],
            "answer": answer
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing query: {str(e)}")
