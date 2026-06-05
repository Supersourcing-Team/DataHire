import logging
from typing import List
import google.generativeai as genai
from app.core.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Singleton service for generating vector embeddings across the platform.
    Using Gemini text-embedding-004 with 384 dimensions.
    """
    _instance = None

    def __new__(cls, model_name: str = "models/text-embedding-004"):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance._initialize(model_name)
        return cls._instance

    def _initialize(self, model_name: str):
        self.model_name = model_name
        self.dimension = 384  # Matches database schema
        logger.info(f"Initializing EmbeddingService with Gemini model: {model_name}")
        try:
            genai.configure(api_key=settings.GEMINI_API_KEY)
            logger.info("Gemini Embedding configured successfully.")
        except Exception as e:
            logger.error(f"Failed to configure Gemini embedding model: {e}")
            raise e

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional embedding for a single text string.
        Returns a list of floats compatible with pgvector.
        """
        if not text or not text.strip():
            # Return zero vector if text is empty, or handle as needed
            return [0.0] * self.dimension
        
        response = genai.embed_content(
            model=self.model_name,
            content=text,
            task_type="retrieval_document",
            output_dimensionality=self.dimension
        )
        return response['embedding']

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of text strings in batch.
        """
        if not texts:
            return []
            
        response = genai.embed_content(
            model=self.model_name,
            content=texts,
            task_type="retrieval_document",
            output_dimensionality=self.dimension
        )
        return response['embedding']

# Export a default instance for easy imports across the app
embedding_service = EmbeddingService()
