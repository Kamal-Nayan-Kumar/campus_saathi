from llama_index.core.node_parser import MarkdownNodeParser
from llama_index.core import Document
from llama_index.core.schema import TextNode
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings
import uuid
from typing import List

class VectorStoreManager:
    def __init__(self):
        self.chroma_client = chromadb.PersistentClient(
            path="./chroma_db",
            settings=Settings(allow_reset=False)
        )
        self.embedding_model = SentenceTransformer("google/embeddinggemma-300m")
        
    def process_and_store(self, markdown_text: str, doc_category: str):
        """
        Step 3: Chunk markdown using LlamaIndex MarkdownNodeParser
        Step 4: Vectorize and store in ChromaDB
        """
        # Step 3: Chunking
        parser = MarkdownNodeParser()
        document = Document(text=markdown_text, metadata={"category": doc_category})
        nodes = parser.get_nodes_from_documents([document])
        
        # Step 4: Vectorization and Storage
        collection = self.chroma_client.get_or_create_collection(
            name="college_documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        for node in nodes:
            node_text = node.get_content()
            embedding = self.embedding_model.encode(node_text).tolist()
            
            collection.add(
                ids=[str(uuid.uuid4())],
                embeddings=[embedding],
                documents=[node_text],
                metadatas=[{"category": doc_category}]
            )
        
        return len(nodes)
    
    def retrieve_relevant_chunks(self, query: str, top_k: int = 5) -> List[str]:
        """
        Step 5: Retrieve relevant chunks for query
        """
        collection = self.chroma_client.get_or_create_collection(
            name="college_documents",
            metadata={"hnsw:space": "cosine"}
        )
        
        query_embedding = self.embedding_model.encode(query).tolist()
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        return results['documents'][0] if results['documents'] else []
