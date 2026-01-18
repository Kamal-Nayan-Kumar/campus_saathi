from google import genai
from google.genai import types
import os
import time
from .database import DatabaseManager

class PDFProcessor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        self.client = genai.Client(api_key=api_key)
        self.db_manager = DatabaseManager()

    def process_and_ingest(self, file_path: str, filename: str):
        print(f"Processing {filename}...")
        
        # Step 1: Parse to Markdown
        markdown_content = self._parse_pdf(file_path)
        
        if not markdown_content:
            raise Exception("Failed to extract content from PDF")

        # Step 2: Ingest to Astra DB
        try:
            collection = self.db_manager.get_collection()
            
            # Insert with server-side vectorization
            result = collection.insert_one({
                "content": markdown_content,
                "filename": filename,
                "$vectorize": markdown_content
            })
            
            print(f"Successfully ingested {filename} into Astra DB (ID: {result.inserted_id})")
            return True
        except Exception as e:
            print(f"Ingestion error: {e}")
            raise e

    def _parse_pdf(self, path: str) -> str:
        system_instruction = """You are a document parser. Convert this PDF to clean Markdown.
        - Preserve tables using Markdown syntax.
        - Keep headers and structure.
        - Ignore page numbers."""
        
        try:
            with open(path, 'rb') as f:
                pdf_file = self.client.files.upload(
                    file=f,
                    config={'mime_type': 'application/pdf'}
                )
            
            # Wait loop
            while pdf_file.state == 'PROCESSING':
                time.sleep(2)
                pdf_file = self.client.files.get(name=pdf_file.name)

            if pdf_file.state == 'FAILED':
                raise Exception("Gemini File Processing Failed")

            response = self.client.models.generate_content(
                model="gemini-3-pro-preview",
                contents=[
                    pdf_file,
                    "Convert this document to Markdown."
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction
                )
            )
            
            self.client.files.delete(name=pdf_file.name)
            return response.text
        except Exception as e:
            print(f"Parsing error: {e}")
            raise e