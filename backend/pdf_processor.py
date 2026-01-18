from google import genai
from google.genai import types
import os
import time
from llama_index.core.node_parser import SentenceSplitter
from .database import DatabaseManager

class PDFProcessor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found")
        self.client = genai.Client(api_key=api_key)
        self.db_manager = DatabaseManager()
        # Initialize splitter (approx 512 tokens -> ~2000 chars, but safer to go lower for NVIDIA)
        # NVIDIA limit is 512 tokens. Let's aim for 400 tokens per chunk.
        self.splitter = SentenceSplitter(chunk_size=400, chunk_overlap=50)

    def process_and_ingest(self, file_path: str, filename: str):
        print(f"Processing {filename}...")
        
        # Step 1: Parse to Markdown
        markdown_content = self._parse_pdf(file_path)
        
        if not markdown_content:
            raise Exception("Failed to extract content from PDF")

        # Step 2: Chunk Content
        chunks = self.splitter.split_text(markdown_content)
        print(f"Split document into {len(chunks)} chunks.")

        # Step 3: Ingest Chunks to Astra DB
        try:
            collection = self.db_manager.get_collection()
            documents_to_insert = []
            
            for i, chunk_text in enumerate(chunks):
                documents_to_insert.append({
                    "content": chunk_text,
                    "filename": filename,
                    "chunk_index": i,
                    "$vectorize": chunk_text
                })
            
            # Batch insert
            if documents_to_insert:
                result = collection.insert_many(documents_to_insert)
                print(f"Successfully ingested {len(result.inserted_ids)} chunks from {filename} into Astra DB")
            
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
                model="gemini-3-flash-preview",
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
