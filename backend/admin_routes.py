from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import os
import shutil
import traceback

from backend.pdf_processor import PDFProcessor
from backend.vector_store import VectorStoreManager

router = APIRouter()

# Initialize outside the route to catch initialization errors
try:
    pdf_processor = PDFProcessor()
    print("✅ PDFProcessor initialized")
except Exception as e:
    print(f"❌ Failed to initialize PDFProcessor: {e}")
    pdf_processor = None

try:
    vector_store = VectorStoreManager()
    print("✅ VectorStoreManager initialized")
except Exception as e:
    print(f"❌ Failed to initialize VectorStoreManager: {e}")
    vector_store = None

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(...)
):
    """
    Admin uploads PDF document
    Steps 1-4: Upload, Parse, Chunk, Vectorize
    """
    file_path = None
    
    try:
        print(f"\n{'='*50}")
        print(f"📤 NEW UPLOAD REQUEST")
        print(f"File: {file.filename}")
        print(f"Category: {category}")
        print(f"Content-Type: {file.content_type}")
        print(f"{'='*50}\n")
        
        # Check if processors are initialized
        if pdf_processor is None:
            raise HTTPException(status_code=500, detail="PDFProcessor not initialized. Check GEMINI_API_KEY.")
        
        if vector_store is None:
            raise HTTPException(status_code=500, detail="VectorStoreManager not initialized.")
        
        # Validate file type
        if not file.filename.endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Step 1: Save uploaded file
        file_path = os.path.join("uploads", file.filename)
        print(f"💾 Step 1: Saving file to {file_path}")
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(file_path)
        print(f"✅ File saved successfully ({file_size} bytes)")
        
        # Step 2: Parse PDF to Markdown using Gemini 2.5 Pro
        print(f"🤖 Step 2: Parsing PDF with Gemini 2.5 Pro...")
        markdown_content = pdf_processor.parse_pdf_to_markdown(file_path)
        print(f"✅ Markdown generated ({len(markdown_content)} characters)")
        
        # Step 3-4: Chunk and Vectorize
        print(f"🔢 Step 3-4: Chunking and vectorizing...")
        num_chunks = vector_store.process_and_store(markdown_content, category)
        print(f"✅ Created {num_chunks} chunks and stored in ChromaDB")
        
        print(f"\n{'='*50}")
        print(f"✅ SUCCESS: Document processed")
        print(f"{'='*50}\n")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Document processed successfully",
                "filename": file.filename,
                "category": category,
                "chunks_created": num_chunks,
                "markdown_length": len(markdown_content)
            }
        )
    
    except HTTPException as he:
        # Re-raise HTTP exceptions as-is
        print(f"❌ HTTP Exception: {he.detail}")
        raise he
    
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"\n{'='*50}")
        print(f"❌ ERROR OCCURRED")
        print(f"Error: {str(e)}")
        print(f"Traceback:\n{error_trace}")
        print(f"{'='*50}\n")
        
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Error processing document: {str(e)}",
                "error_type": type(e).__name__
            }
        )
    
    finally:
        # Clean up uploaded file
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"🧹 Cleaned up: {file_path}")
            except Exception as cleanup_error:
                print(f"⚠️ Failed to cleanup {file_path}: {cleanup_error}")
