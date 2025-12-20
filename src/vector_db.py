"""
Vector Database - Redis Vector Search
"""

import json
import numpy as np
from typing import List, Dict, Optional
from loguru import logger
import redis
from redis import ConnectionPool
from redis.commands.search.field import TextField, VectorField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query


class VectorDB:
    """Redis Vector Database with semantic search"""

    @staticmethod
    def escape_redis_query(value: str) -> str:
        """
        Properly escape Redis search query values to prevent injection

        Args:
            value: String value to escape

        Returns:
            Escaped string safe for Redis search queries
        """
        # Redis search special characters that need escaping
        special_chars = [
            '\\',  # Backslash must be escaped first
            '"',   # Double quotes
            '@',   # Field selector
            '|',   # OR operator
            '{',   # Tag delimiter
            '}',   # Tag delimiter
            '[',   # Numeric range
            ']',   # Numeric range
            '(',   # Grouping
            ')',   # Grouping
            '*',   # Wildcard
            '~',   # Fuzzy match
            '-',   # NOT operator (when at start)
            ':',   # Field separator
            ';',   # Command separator
            ',',   # List separator
        ]

        escaped = value
        for char in special_chars:
            escaped = escaped.replace(char, f'\\{char}')

        return escaped

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
            # Create connection pool for better concurrent performance
            pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                max_connections=20,  # Allow up to 20 concurrent connections
                decode_responses=False,
                socket_keepalive=True,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            self.client = redis.Redis(connection_pool=pool)
            self.client.ping()
            logger.success(f"Connected to Redis at {host}:{port} (pool size: 20)")
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
        """
        Get total number of unique PDF files (optimized with SCAN + pipeline)

        Performance improvements:
        - Uses SCAN instead of KEYS to avoid blocking Redis
        - Batches operations with pipeline to reduce round trips
        - Only fetches filename field instead of entire document
        """
        try:
            filenames = set()
            batch_size = 100  # Process keys in batches
            key_batch = []

            # Use SCAN to iterate keys without blocking Redis
            # Only scan numeric doc:N keys (doc:0, doc:1, etc.)
            for key in self.client.scan_iter(match="doc:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Filter to only numeric document keys (doc:0, doc:1, etc.)
                # Exclude doc:hash:xxx keys used for duplicate tracking
                if not key_str.split(':')[-1].isdigit():
                    continue

                key_batch.append(key)

                # Process batch when it reaches batch_size
                if len(key_batch) >= batch_size:
                    self._process_key_batch(key_batch, filenames)
                    key_batch = []

            # Process remaining keys
            if key_batch:
                self._process_key_batch(key_batch, filenames)

            return len(filenames)
        except Exception as e:
            logger.error(f"Error counting unique files: {e}")
            return 0

    def _process_key_batch(self, keys: List[bytes], filenames: set):
        """
        Process a batch of keys using Redis pipeline for efficiency

        Args:
            keys: List of Redis keys to process
            filenames: Set to add unique filenames to
        """
        if not keys:
            return

        # Use pipeline to batch all operations
        pipe = self.client.pipeline()
        for key in keys:
            pipe.type(key)
            pipe.hget(key, 'filename')
        results = pipe.execute()

        # Process results (pairs of type and filename)
        for i in range(0, len(results), 2):
            key_type = results[i]
            filename = results[i + 1]

            # Only process hash keys with filename field
            if key_type == b'hash' and filename:
                filenames.add(filename.decode('utf-8'))

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
            # Escape special characters in filename for Redis search (prevent injection)
            escaped_filename = self.escape_redis_query(filename)
            query = Query(f'@filename:"{escaped_filename}"').return_fields("filename").dialect(2)
            results = self.client.ft(self.index_name).search(query)
            return results.total
        except Exception as e:
            logger.error(f"Failed to count documents for {filename}: {e}")
            return 0

    def batch_count_documents_by_filenames(self, filenames: List[str]) -> Dict[str, int]:
        """
        Count number of chunks for multiple filenames in a single efficient operation

        This avoids N+1 queries by batching all counts together.

        Args:
            filenames: List of filenames to count chunks for

        Returns:
            Dictionary mapping filename to chunk count
        """
        if not filenames:
            return {}

        try:
            # Initialize result dictionary with all filenames
            result = {filename: 0 for filename in filenames}

            # For batch counting, we need to query each filename but can optimize
            # by using async operations or by getting all docs and grouping
            # Since Redis search doesn't support OR queries efficiently for this use case,
            # we'll use a different approach: get all indexed documents once and group by filename

            # Get all document keys efficiently using SCAN
            filename_counts = {}
            batch_size = 100
            key_batch = []

            for key in self.client.scan_iter(match="doc:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Filter to only numeric document keys (doc:0, doc:1, etc.)
                if not key_str.split(':')[-1].isdigit():
                    continue

                key_batch.append(key)

                # Process batch when it reaches batch_size
                if len(key_batch) >= batch_size:
                    self._count_filenames_in_batch(key_batch, filename_counts, set(filenames))
                    key_batch = []

            # Process remaining keys
            if key_batch:
                self._count_filenames_in_batch(key_batch, filename_counts, set(filenames))

            # Update result with actual counts
            for filename in filenames:
                result[filename] = filename_counts.get(filename, 0)

            return result
        except Exception as e:
            logger.error(f"Failed to batch count documents: {e}")
            # Return zero counts for all filenames on error
            return {filename: 0 for filename in filenames}

    def _count_filenames_in_batch(self, keys: List[bytes], filename_counts: Dict[str, int], target_filenames: set):
        """
        Count occurrences of filenames in a batch of keys

        Args:
            keys: List of Redis keys to process
            filename_counts: Dictionary to update with counts
            target_filenames: Set of filenames we're interested in (for filtering)
        """
        if not keys:
            return

        # Use pipeline to batch all operations
        pipe = self.client.pipeline()
        for key in keys:
            pipe.hget(key, 'filename')
        results = pipe.execute()

        # Count filenames
        for filename_bytes in results:
            if filename_bytes:
                filename = filename_bytes.decode('utf-8')
                # Only count if this is one of the target filenames
                if filename in target_filenames:
                    filename_counts[filename] = filename_counts.get(filename, 0) + 1

    def get_chunks_by_filename(self, filename: str) -> List[Dict]:
        """
        Get all chunks for a specific filename

        Args:
            filename: Name of the file to get chunks for

        Returns:
            List of chunks with their text and metadata
        """
        try:
            # Escape special characters in filename for Redis search (prevent injection)
            escaped_filename = self.escape_redis_query(filename)

            # Query all chunks for this filename, sorted by chunk_index
            query = (
                Query(f'@filename:"{escaped_filename}"')
                .return_fields("text", "filename", "source", "chunk_index")
                .sort_by("chunk_index", asc=True)
                .paging(0, 10000)  # Get up to 10000 chunks
                .dialect(2)
            )

            results = self.client.ft(self.index_name).search(query)

            # Parse results
            chunks = []
            for doc in results.docs:
                chunk_data = {
                    "text": doc.text if hasattr(doc, 'text') else "",
                    "filename": doc.filename if hasattr(doc, 'filename') else filename,
                    "source": doc.source if hasattr(doc, 'source') else "",
                    "chunk_index": int(doc.chunk_index) if hasattr(doc, 'chunk_index') else 0,
                    "page": doc.source if hasattr(doc, 'source') else "N/A",
                    "metadata": {
                        "chunk_index": int(doc.chunk_index) if hasattr(doc, 'chunk_index') else 0,
                        "source": doc.source if hasattr(doc, 'source') else ""
                    }
                }
                chunks.append(chunk_data)

            logger.info(f"Retrieved {len(chunks)} chunks for {filename}")
            return chunks

        except Exception as e:
            logger.error(f"Failed to get chunks for {filename}: {e}")
            return []

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
            # Escape special characters in filename for Redis search (prevent injection)
            escaped_filename = self.escape_redis_query(filename)
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
