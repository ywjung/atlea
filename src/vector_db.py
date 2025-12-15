"""
Vector Database - Redis Vector Search
"""

import json
import numpy as np
from typing import List, Dict, Optional
from loguru import logger
import redis
from redis.commands.search.field import TextField, VectorField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query


class VectorDB:
    """Redis Vector Database with semantic search"""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        index_name: str = "pdf_index",
        embedding_dim: int = 1024
    ):
        """
        Initialize Redis Vector Database

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            index_name: Name for search index
            embedding_dim: Dimension of embeddings
        """
        self.index_name = index_name
        self.embedding_dim = embedding_dim

        try:
            self.client = redis.Redis(
                host=host,
                port=port,
                db=db,
                decode_responses=False
            )
            self.client.ping()
            logger.success(f"Connected to Redis at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        self._create_index()

    def _create_index(self):
        """Create or recreate search index"""
        try:
            # Try to get index info
            self.client.ft(self.index_name).info()
            logger.info(f"Index '{self.index_name}' already exists")
        except:
            # Create new index
            logger.info(f"Creating new index '{self.index_name}'")
            schema = (
                TextField("text"),
                TextField("filename"),
                TextField("source"),
                NumericField("chunk_index"),
                VectorField(
                    "embedding",
                    "FLAT",
                    {
                        "TYPE": "FLOAT32",
                        "DIM": self.embedding_dim,
                        "DISTANCE_METRIC": "COSINE",
                    }
                ),
            )

            definition = IndexDefinition(
                prefix=["doc:"],
                index_type=IndexType.HASH
            )

            try:
                self.client.ft(self.index_name).create_index(
                    fields=schema,
                    definition=definition
                )
                logger.success(f"Index '{self.index_name}' created successfully")
            except Exception as e:
                logger.error(f"Failed to create index: {e}")
                raise

    def add_documents(self, documents: List[Dict], embeddings: List[List[float]]):
        """
        Add documents with embeddings to database

        Args:
            documents: List of document dictionaries
            embeddings: List of embedding vectors
        """
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")

        pipe = self.client.pipeline()
        for idx, (doc, embedding) in enumerate(zip(documents, embeddings)):
            doc_id = f"doc:{idx}"

            # Convert embedding to bytes
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

            # Prepare document
            doc_data = {
                "text": doc.get("text", ""),
                "filename": doc.get("filename", ""),
                "source": doc.get("source", ""),
                "chunk_index": doc.get("chunk_index", 0),
                "embedding": embedding_bytes
            }

            pipe.hset(doc_id, mapping=doc_data)

        pipe.execute()
        logger.success(f"Added {len(documents)} documents to database")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_expr: Optional[str] = None
    ) -> List[Dict]:
        """
        Search for similar documents

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filter_expr: Optional filter expression

        Returns:
            List of matching documents with scores
        """
        try:
            # Convert query embedding to bytes
            query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

            # Build query
            base_query = f"*=>[KNN {top_k} @embedding $vec AS score]"
            if filter_expr:
                base_query = f"({filter_expr})=>[KNN {top_k} @embedding $vec AS score]"

            query = (
                Query(base_query)
                .sort_by("score")
                .return_fields("text", "filename", "source", "chunk_index", "score")
                .dialect(2)
            )

            # Execute search
            results = self.client.ft(self.index_name).search(
                query,
                query_params={"vec": query_bytes}
            )

            # Parse results
            documents = []
            for doc in results.docs:
                documents.append({
                    "text": doc.text,
                    "filename": doc.filename,
                    "source": doc.source,
                    "chunk_index": int(doc.chunk_index),
                    "score": float(doc.score)
                })

            logger.debug(f"Found {len(documents)} matching documents")
            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def count_documents(self) -> int:
        """Get total number of documents (chunks) in database"""
        try:
            info = self.client.ft(self.index_name).info()
            return int(info.get("num_docs", 0))
        except:
            return 0

    def count_unique_files(self) -> int:
        """Get total number of unique PDF files"""
        try:
            # Get all document keys
            keys = self.client.keys("doc:*")
            if not keys:
                return 0

            # Get unique filenames
            filenames = set()
            for key in keys:
                doc = self.client.hgetall(key)
                if doc and b'filename' in doc:
                    filenames.add(doc[b'filename'].decode('utf-8'))

            return len(filenames)
        except Exception as e:
            logger.error(f"Error counting unique files: {e}")
            return 0

    def is_indexed(self) -> bool:
        """
        Check if database has been indexed

        Returns:
            True if index exists and has documents
        """
        try:
            return self.count_documents() > 0
        except:
            return False

    def save_index_state(self, metadata: Dict):
        """
        Save indexing state metadata to Redis

        Args:
            metadata: Dictionary with indexing metadata
        """
        try:
            self.client.set(
                "index:state",
                json.dumps(metadata, ensure_ascii=False)
            )
            logger.debug("Index state saved")
        except Exception as e:
            logger.error(f"Failed to save index state: {e}")

    def get_index_state(self) -> Optional[Dict]:
        """
        Get indexing state metadata from Redis

        Returns:
            Dictionary with indexing metadata or None
        """
        try:
            state = self.client.get("index:state")
            if state:
                return json.loads(state)
            return None
        except Exception as e:
            logger.error(f"Failed to get index state: {e}")
            return None

    def count_documents_by_filename(self, filename: str) -> int:
        """
        Count number of chunks for a specific filename

        Args:
            filename: Name of the file to count chunks for

        Returns:
            Number of chunks for the specified filename
        """
        try:
            # Escape special characters in filename for Redis search
            # Use exact match with quotes for TextField
            escaped_filename = filename.replace('"', '\\"')
            query = Query(f'@filename:"{escaped_filename}"').return_fields("filename").dialect(2)
            results = self.client.ft(self.index_name).search(query)
            return results.total
        except Exception as e:
            logger.error(f"Failed to count documents for {filename}: {e}")
            return 0

    def delete_by_filename(self, filename: str) -> int:
        """
        Delete all chunks associated with a filename

        Args:
            filename: Name of the file whose chunks should be deleted

        Returns:
            Number of chunks deleted
        """
        try:
            # Find all document IDs for this filename
            query = Query(f"@filename:{{{filename}}}").return_fields("filename").dialect(2)
            results = self.client.ft(self.index_name).search(query)

            deleted_count = 0
            pipe = self.client.pipeline()

            for doc in results.docs:
                pipe.delete(doc.id)
                deleted_count += 1

            if deleted_count > 0:
                pipe.execute()
                logger.info(f"Deleted {deleted_count} chunks for {filename}")

            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete documents for {filename}: {e}")
            return 0

    def sample_documents_by_filename(self, filename: str, limit: int = 3) -> List[Dict]:
        """
        Get random sample of documents for a specific filename

        Args:
            filename: Name of the file to sample from
            limit: Number of documents to sample

        Returns:
            List of sampled documents
        """
        try:
            # Escape special characters in filename for Redis search
            escaped_filename = filename.replace('"', '\\"')
            query = Query(f'@filename:"{escaped_filename}"').return_fields("text", "filename", "source", "chunk_index").paging(0, limit).dialect(2)
            results = self.client.ft(self.index_name).search(query)

            documents = []
            for doc in results.docs:
                documents.append({
                    "text": doc.text,
                    "filename": doc.filename,
                    "source": doc.source if hasattr(doc, 'source') else "",
                    "chunk_index": int(doc.chunk_index) if hasattr(doc, 'chunk_index') else 0
                })

            return documents
        except Exception as e:
            logger.error(f"Failed to sample documents for {filename}: {e}")
            return []

    def clear_index(self):
        """Clear all documents from index"""
        try:
            self.client.ft(self.index_name).dropindex(delete_documents=True)
            logger.info("Index cleared")
            # Clear index state
            self.client.delete("index:state")
            self._create_index()
        except Exception as e:
            logger.error(f"Failed to clear index: {e}")
            raise

    def close(self):
        """Close Redis connection"""
        self.client.close()
        logger.info("Redis connection closed")
