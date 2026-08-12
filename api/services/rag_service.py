
import logging
import numpy as np
import faiss
from api.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)

class RAGService:
    """
    In-memory RAG using FAISS and OpenAI Embeddings.
    Scoped to a single extraction session (not persistent across requests).
    """

    def __init__(self):
        self.llm_client = LLMClient()
        self.dimension = 1536 # text-embedding-3-small dimension
        self.index = faiss.IndexFlatL2(self.dimension)
        self.chunks = [] # Keep original text mapped to index
    
    def chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 100) -> list:
        """
        Simple sliding window chunker.
        """
        tokens = text.split() # Naive whitespace tokenization for speed
        if not tokens:
            return []
            
        chunks = []
        for i in range(0, len(tokens), chunk_size - overlap):
            chunk_tokens = tokens[i : i + chunk_size]
            chunks.append(" ".join(chunk_tokens))
            
        return chunks

    def add_text(self, text: str):
        """
        Chunks text, embeds it, and adds to FAISS index.
        """
        try:
            logger.info(f"RAG: Chunking text of length {len(text)}...")
            new_chunks = self.chunk_text(text)
            
            if not new_chunks:
                return

            embeddings = []
            valid_chunks = []

            for chunk in new_chunks:
                try:
                    emb = self.llm_client.get_embedding(chunk)
                    embeddings.append(emb)
                    valid_chunks.append(chunk)
                except Exception as e:
                    logger.warning(f"RAG: Failed to embed chunk: {e}")

            if not embeddings:
                return

            # Convert to float32 numpy array for FAISS
            vector_data = np.array(embeddings).astype('float32')
            
            self.index.add(vector_data)
            self.chunks.extend(valid_chunks)
            
            logger.info(f"RAG: Added {len(valid_chunks)} chunks to index. Total: {self.index.ntotal}")

        except Exception as e:
            logger.error(f"RAG: add_text failed: {e}", exc_info=True)

    def retrieve(self, query: str, k: int = 4) -> str:
        """
        Retrieves top-k relevant chunks as a single context string.
        """
        try:
            if self.index.ntotal == 0:
                return ""

            # Embed query
            query_emb = self.llm_client.get_embedding(query)
            query_vec = np.array([query_emb]).astype('float32')

            # Search
            distances, indices = self.index.search(query_vec, k)
            
            results = []
            for idx in indices[0]:
                if idx != -1 and idx < len(self.chunks):
                    results.append(self.chunks[idx])

            return "\n\n...[Snippet]...\n".join(results)
            
        except Exception as e:
            logger.error(f"RAG: retrieve failed: {e}", exc_info=True)
            return ""

    def retrieve_multiple(self, queries: list, k_per_query: int = 3) -> str:
        """
        Retrieves chunks for multiple queries and deduplicates them.
        """
        try:
            if self.index.ntotal == 0:
                return ""

            unique_indices = set()
            
            for query in queries:
                try:
                    query_emb = self.llm_client.get_embedding(query)
                    query_vec = np.array([query_emb]).astype('float32')
                    
                    distances, indices = self.index.search(query_vec, k_per_query)
                    
                    for idx in indices[0]:
                        if idx != -1 and idx < len(self.chunks):
                            unique_indices.add(idx)
                except Exception as e:
                     logger.warning(f"RAG: Query failed '{query}': {e}")
                     continue

            # Sort indices to maintain document order (better for context flow)
            sorted_indices = sorted(list(unique_indices))
            
            results = [self.chunks[idx] for idx in sorted_indices]
            
            return "\n\n...[Snippet]...\n".join(results)
            
        except Exception as e:
             logger.error(f"RAG: retrieve_multiple failed: {e}", exc_info=True)
             return ""
