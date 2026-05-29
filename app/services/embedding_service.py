import logging
from typing import List

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Singleton service for generating vector embeddings across the platform.
    Using all-MiniLM-L6-v2 which produces 384-dimensional vectors.
    """
    _instance = None

    def __new__(cls, model_name: str = "all-MiniLM-L6-v2"):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
            cls._instance._initialize(model_name)
        return cls._instance

    def _initialize(self, model_name: str):
        self.model_name = model_name
        self.dimension = 1536  # Fixed dimension for all-MiniLM-L6-v2
        logger.info(f"Initializing EmbeddingService with model: {model_name}")
        try:
            from sentence_transformers import SentenceTransformer
            # Load the model (this will download it on first run)
            self.model = SentenceTransformer(self.model_name)
            logger.info("SentenceTransformer model loaded successfully.")
        except ImportError:
            logger.error("sentence-transformers is not installed. Please install it.")
            raise
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise e

    def get_embedding(self, text: str) -> List[float]:
        """
        Generates a 384-dimensional embedding for a single text string.
        Returns a list of floats compatible with pgvector.
        """
        if not text or not text.strip():
            # Return zero vector if text is empty, or handle as needed
            return [0.0] * self.dimension
        
        # encode returns a numpy array, convert to list
        embedding = self.model.encode(text)
        return embedding.tolist()

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates embeddings for a list of text strings in batch.
        """
        if not texts:
            return []
            
        embeddings = self.model.encode(texts)
        return embeddings.tolist()

# Export a default instance for easy imports across the app
embedding_service = EmbeddingService()
