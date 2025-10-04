from google import genai
from google.genai import types
import os
import io

class PDFProcessor:
    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment")
        self.client = genai.Client(api_key=api_key)
        
    def parse_pdf_to_markdown(self, pdf_path: str) -> str:
        """
        Step 2: Parse PDF using Gemini 2.5 Pro with VLM capabilities
        Upload file first, then process
        """
        system_instruction = """You are a document parser. Convert the PDF content to clean Markdown format.
        
Rules:
1. Reconstruct tables accurately using Markdown table syntax (| Column | Column |)
2. Use # for main headings, ## for subheadings, ### for sub-subheadings
3. Remove page numbers, headers, and footers
4. Preserve the hierarchy and structure of the document
5. Ensure tables are properly formatted with alignment markers
6. Keep all content semantic and well-organized"""
        
        try:
            # Upload PDF file using File API
            with open(pdf_path, 'rb') as f:
                pdf_file = self.client.files.upload(
                    file=f,
                    config={'mime_type': 'application/pdf'}
                )
            
            print(f"✓ Uploaded file: {pdf_file.name}")
            
            # Wait for file to be processed
            import time
            max_wait = 60  # 60 seconds max wait
            wait_time = 0
            while pdf_file.state == 'PROCESSING' and wait_time < max_wait:
                time.sleep(2)
                pdf_file = self.client.files.get(name=pdf_file.name)
                wait_time += 2
                print(f"⏳ Processing file... ({wait_time}s)")
            
            if pdf_file.state == 'FAILED':
                raise Exception(f"File processing failed: {pdf_file.error}")
            
            print(f"✓ File ready: {pdf_file.state}")
            
            # Generate content with the uploaded file
            response = self.client.models.generate_content(
                model="gemini-2.5-pro",
                contents=[
                    pdf_file,
                    "Convert this PDF document to clean Markdown format following the system instructions."
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.1
                )
            )
            
            # Clean up - delete the uploaded file
            self.client.files.delete(name=pdf_file.name)
            print(f"✓ Cleaned up uploaded file")
            
            return response.text
            
        except Exception as e:
            print(f"❌ Error in PDF processing: {str(e)}")
            raise Exception(f"PDF parsing failed: {str(e)}")
