import os
from openai import OpenAI
from pypdf import PdfReader
from llama_index.core.node_parser import SentenceSplitter
from .database import DatabaseManager

class PDFProcessor:
    def __init__(self):
        self.api_key = os.getenv("OPENCODE_API_KEY") or os.getenv("OPENCODE_GO_API_KEY")
        if not self.api_key:
            raise ValueError("OPENCODE_API_KEY (or OPENCODE_GO_API_KEY) not found")
        
        self.base_url = "https://opencode.ai/zen/go/v1"
        self.model = "deepseek-v4-flash"
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        self.db_manager = DatabaseManager()
        self.splitter = SentenceSplitter(chunk_size=256, chunk_overlap=20)

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
        try:
            reader = PdfReader(path)
            full_markdown = []
            
            system_instruction = """You are a document parser. Convert this raw text extracted from a PDF page into clean Markdown.
- Preserve tables using Markdown table syntax.
- Keep headers and document structure.
- Ignore page numbers and running headers/footers.
- Return ONLY the formatted Markdown. Do not include any intro/outro comments or formatting backticks like ```markdown."""

            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if not text or not text.strip():
                    continue
                
                print(f"Formatting page {i+1}/{len(reader.pages)}...")
                
                # Use OpenCode Go to clean and format the text
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": text}
                    ],
                    temperature=0.1
                )
                
                page_markdown = response.choices[0].message.content
                if page_markdown:
                    full_markdown.append(page_markdown.strip())
            
            return "\n\n".join(full_markdown)
        except Exception as e:
            print(f"Parsing error: {e}")
            raise e
