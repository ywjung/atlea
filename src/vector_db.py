"""
Vector Database - Redis Vector Search
"""

import hashlib
import json
import numpy as np
from typing import List, Dict, Optional
from loguru import logger
import redis
from redis import ConnectionPool
from redis.commands.search.field import TextField, VectorField, NumericField, TagField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query


class VectorDB:
    """Redis Vector Database with semantic search"""

    @staticmethod
    def escape_redis_query(value: str) -> str:
        """
        Escape Redis search query values for TextField phrase searches (with quotes)

        For TextField with quote-based phrase matching, only backslash and quotes
        need to be escaped. Other characters are treated as literals inside quotes.

        Args:
            value: String value to escape

        Returns:
            Escaped string safe for Redis search queries
        """
        # For TextField phrase searches with quotes, only escape:
        # 1. Backslash (must be first)
        # 2. Double quotes
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return escaped

    @staticmethod
    def escape_tag_value(value: str) -> str:
        """
        Escape Redis search query values for TagField

        TagField special characters that need escaping: , . < > { } [ ] " ' : ; ! @ # $ % ^ & * ( ) - + = ~

        Args:
            value: String value to escape

        Returns:
            Escaped string safe for TagField queries
        """
        # Escape special characters for TagField
        special_chars = r',.<>{}[]"\':;!@#$%^&*()-+=~ '

        # Build escaped string character by character to avoid double-escaping
        escaped = ''
        for char in value:
            if char in special_chars:
                escaped += '\\' + char
            else:
                escaped += char

        return escaped

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        index_name: str = "pdf_index",
        embedding_dim: int = 1024,
        max_connections: int = 50,
        socket_timeout: int = 5,
        socket_keepalive: bool = True,
        socket_keepalive_options: Optional[dict] = None,
        health_check_interval: int = 30
    ):
        """
        Initialize Redis Vector Database

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            index_name: Name for search index
            embedding_dim: Dimension of embeddings
            max_connections: Maximum number of connections in pool
            socket_timeout: Socket timeout in seconds
            socket_keepalive: Enable TCP keepalive
            socket_keepalive_options: TCP keepalive options dict
            health_check_interval: Connection health check interval in seconds
        """
        self.index_name = index_name
        self.embedding_dim = embedding_dim

        try:
            # Create simple connection pool (disable health_check for faster startup)
            pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                max_connections=max_connections,
                decode_responses=False,
                socket_connect_timeout=socket_timeout,
                socket_timeout=socket_timeout,
                retry_on_timeout=True,
                health_check_interval=0  # Disable health check to avoid blocking
            )
            self.client = redis.Redis(connection_pool=pool)
            logger.success(f"Connected to Redis at {host}:{port} (pool: {max_connections} connections, timeout: {socket_timeout}s)")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Create or verify index (needed when schema changes)
        self._create_index()

    def _create_index(self):
        """Create or recreate search index"""
        try:
            # Try to get index info with timeout
            logger.info(f"Checking if index '{self.index_name}' exists...")
            self.client.ft(self.index_name).info()
            logger.info(f"Index '{self.index_name}' already exists")
        except Exception as e:
            logger.warning(f"Index check failed or doesn't exist: {e}")
            # Create new index
            logger.info(f"Creating new index '{self.index_name}'")
            schema = (
                TextField("text"),
                TextField("filename", sortable=True),  # Use TextField with tokenization for full-text search
                TagField("filename_exact", separator="|"),  # TagField for exact filename matching (deprecated for Korean)
                TagField("filename_hash", separator="|"),  # MD5 hash of filename for Unicode support
                TextField("source"),
                NumericField("chunk_index"),
                TagField("group_id", separator="|"),  # Support OR search across groups
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

        # Get default group ID if no group specified
        default_group_id = self.client.get('group:default')
        if default_group_id:
            default_group_id = default_group_id.decode('utf-8')
        else:
            default_group_id = ''  # Will be set during migration

        import uuid

        # Cache for filename -> group_id mapping to avoid repeated Redis calls
        filename_group_cache = {}

        pipe = self.client.pipeline()
        for idx, (doc, embedding) in enumerate(zip(documents, embeddings)):
            # Generate unique document ID using UUID to avoid overwriting
            doc_id = f"doc:{uuid.uuid4().hex}"

            # Convert embedding to bytes
            embedding_bytes = np.array(embedding, dtype=np.float32).tobytes()

            # Prepare document
            filename = doc.get("filename", "")
            # Calculate MD5 hash of filename for Unicode-safe TAG field
            filename_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()

            # Preserve existing group assignment during reindexing
            if filename not in filename_group_cache:
                existing_group = self.client.get(f'doc:group:{filename}')
                if existing_group:
                    filename_group_cache[filename] = existing_group.decode('utf-8')
                else:
                    filename_group_cache[filename] = default_group_id

            assigned_group_id = doc.get("group_id", filename_group_cache[filename])

            doc_data = {
                "text": doc.get("text", ""),
                "filename": filename,
                "filename_exact": filename,  # Exact filename for TagField matching (deprecated for Korean)
                "filename_hash": filename_hash,  # MD5 hash for Unicode support
                "source": doc.get("source", ""),
                "chunk_index": doc.get("chunk_index", 0),
                "group_id": assigned_group_id,  # Preserve existing group assignment
                "embedding": embedding_bytes
            }

            pipe.hset(doc_id, mapping=doc_data)

        pipe.execute()

        # Wait for Redis Search index to update
        # Redis Search indexing is asynchronous, so we need a small delay
        # to ensure newly added documents are searchable immediately
        import time
        time.sleep(0.2)  # 200ms delay for index propagation

        logger.success(f"Added {len(documents)} documents to database")

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        filter_expr: Optional[str] = None,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Search for similar documents

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filter_expr: Optional filter expression
            group_ids: Optional list of group IDs to filter by (OR logic)
            document_ids: Optional list of document filenames to filter by (OR logic)

        Returns:
            List of matching documents with scores
        """
        try:
            # DIAGNOSTIC: Check what query_embedding actually is
            logger.warning(f"DIAGNOSTIC: query_embedding type: {type(query_embedding)}")
            logger.warning(f"DIAGNOSTIC: query_embedding shape/len: {getattr(query_embedding, 'shape', len(query_embedding) if hasattr(query_embedding, '__len__') else 'no length')}")
            if hasattr(query_embedding, '__len__') and len(query_embedding) < 10:
                logger.warning(f"DIAGNOSTIC: query_embedding content: {query_embedding}")

            # Convert query embedding to bytes
            query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

            # DIAGNOSTIC: Check the actual bytes being sent
            logger.warning(f"DIAGNOSTIC: query_bytes length: {len(query_bytes)} bytes")
            logger.warning(f"DIAGNOSTIC: First 50 bytes of query_bytes: {query_bytes[:50].hex()}")

            # DIAGNOSTIC: Compare with random embedding bytes
            random_emb = np.random.randn(1024).astype(np.float32).tobytes()
            logger.warning(f"DIAGNOSTIC: Random embedding bytes length: {len(random_emb)} bytes")
            logger.warning(f"DIAGNOSTIC: First 50 bytes of random_emb: {random_emb[:50].hex()}")

            # Build filters
            filters = []

            # Group filter (OR logic using TagField)
            if group_ids:
                escaped_groups = [self.escape_tag_value(gid) for gid in group_ids]
                group_filter = "|".join(escaped_groups)
                filters.append(f"@group_id:{{{group_filter}}}")

            # Document filter (OR logic using filename hash for Unicode support)
            if document_ids:
                # Convert filenames to MD5 hashes for Unicode-safe TAG field
                filename_hashes = [hashlib.md5(filename.encode('utf-8')).hexdigest() for filename in document_ids]
                hash_filter = "|".join(filename_hashes)
                filters.append(f"@filename_hash:{{{hash_filter}}}")

            # Custom filter expression
            if filter_expr:
                filters.append(f"({filter_expr})")

            # Combine all filters with AND
            base_query = f"*=>[KNN {top_k} @embedding $vec AS score]"
            if filters:
                # Single filter: no extra parentheses
                # Multiple filters: wrap with parentheses for AND logic
                if len(filters) == 1:
                    combined_filter = filters[0]
                else:
                    combined_filter = "(" + " ".join(filters) + ")"
                base_query = f"{combined_filter}=>[KNN {top_k} @embedding $vec AS score]"
                logger.debug(f"Search filters: {filters}")
                logger.debug(f"Redis query: {base_query}")

            query = (
                Query(base_query)
                .return_fields("text", "filename", "source", "chunk_index", "group_id", "score")
                .dialect(2)
            )

            # Log query details for debugging
            logger.debug(f"Query embedding vector length: {len(query_bytes)} bytes")
            logger.debug(f"First 20 bytes of embedding: {query_bytes[:20].hex()}")
            logger.debug(f"Final query string: {base_query}")
            if filters:
                logger.debug(f"Active filters: {filters}")

            # DIAGNOSTIC: Check index state and test query
            if filters:
                try:
                    # Check index info
                    index_info = self.client.ft(self.index_name).info()
                    num_docs = index_info.get('num_docs', 0)
                    logger.warning(f"DIAGNOSTIC: Index '{self.index_name}' has {num_docs} total documents")

                    # Check how many S2B documents exist
                    s2b_check = self.client.execute_command(
                        'FT.SEARCH', self.index_name,
                        '@filename_exact:{S2B\\ FaQ1\\.pdf}',
                        'LIMIT', '0', '0',
                        'DIALECT', '2'
                    )
                    logger.warning(f"DIAGNOSTIC: {s2b_check[0]} documents match '@filename_exact:{{S2B\\ FaQ1\\.pdf}}'")

                    # Test with random embedding
                    test_embedding = np.random.randn(1024).astype(np.float32).tobytes()

                    # Test WITHOUT SORTBY
                    cmd_args = ['FT.SEARCH', self.index_name, base_query, 'PARAMS', '2', 'vec', 'RETURN', '1', 'filename_exact', 'DIALECT', '2']
                    logger.warning(f"DIAGNOSTIC: Command args: {cmd_args}")
                    logger.warning(f"DIAGNOSTIC: Embedding length: {len(test_embedding)} bytes")
                    direct_result1 = self.client.execute_command(
                        'FT.SEARCH', self.index_name,
                        base_query,
                        'PARAMS', '2', 'vec', test_embedding,
                        'RETURN', '1', 'filename_exact',
                        'DIALECT', '2'
                    )
                    logger.warning(f"DIAGNOSTIC: Hybrid query WITHOUT SORTBY returned {direct_result1[0]} results")

                    # Test WITH SORTBY
                    direct_result2 = self.client.execute_command(
                        'FT.SEARCH', self.index_name,
                        base_query,
                        'PARAMS', '2', 'vec', test_embedding,
                        'RETURN', '1', 'filename_exact',
                        'SORTBY', 'score',
                        'DIALECT', '2'
                    )
                    logger.warning(f"DIAGNOSTIC: Hybrid query WITH SORTBY returned {direct_result2[0]} results")
                except Exception as e:
                    logger.error(f"DIAGNOSTIC failed: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # Execute search using execute_command (Query class has issues with hybrid queries)
            logger.warning(f"ACTUAL SEARCH: Executing with base_query: {base_query}")
            logger.warning(f"ACTUAL SEARCH: query_bytes TYPE: {type(query_bytes)}")
            logger.warning(f"ACTUAL SEARCH: query_bytes length: {len(query_bytes)}")
            logger.warning(f"ACTUAL SEARCH: query_bytes first 20 bytes: {query_bytes[:20].hex()}")
            logger.warning(f"ACTUAL SEARCH: Redis connection: {self.client.connection_pool.connection_kwargs}")

            # TEST: Try with a random embedding to see if it's the embedding that's the issue
            test_bytes = np.random.randn(1024).astype(np.float32).tobytes()
            logger.warning(f"ACTUAL SEARCH: test_bytes TYPE: {type(test_bytes)}")
            logger.warning(f"ACTUAL SEARCH: test_bytes length: {len(test_bytes)}")

            try:
                # Execute search with actual query bytes
                logger.warning(f"SEARCH: base_query={base_query}")
                logger.warning(f"SEARCH: query_bytes length={len(query_bytes)}")

                raw_results = self.client.execute_command(
                    'FT.SEARCH', self.index_name,
                    base_query,
                    'PARAMS', '2', 'vec', query_bytes,
                    'RETURN', '6', 'text', 'filename', 'source', 'chunk_index', 'group_id', 'score',
                    'DIALECT', '2'
                )
                logger.warning(f"SEARCH: Got {raw_results[0]} results from Redis")

            except Exception as e:
                logger.error(f"SEARCH: execute_command failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

            # Parse raw results
            num_results = raw_results[0]
            logger.debug(f"Redis returned {num_results} results")

            # Convert raw results to result objects
            class SearchResult:
                def __init__(self, doc_data):
                    self.docs = []
                    for i in range(1, len(doc_data), 2):
                        doc_dict = {}
                        fields = doc_data[i + 1]
                        for j in range(0, len(fields), 2):
                            key = fields[j].decode() if isinstance(fields[j], bytes) else fields[j]
                            value = fields[j + 1].decode() if isinstance(fields[j + 1], bytes) else fields[j + 1]
                            doc_dict[key] = value

                        # Create a simple object with attributes
                        class Doc:
                            pass
                        doc = Doc()
                        doc.text = doc_dict.get('text', '')
                        doc.filename = doc_dict.get('filename', '')
                        doc.source = doc_dict.get('source', '')
                        doc.chunk_index = doc_dict.get('chunk_index', '0')
                        doc.group_id = doc_dict.get('group_id', '')
                        doc.score = doc_dict.get('score', '0')
                        self.docs.append(doc)

            results = SearchResult(raw_results)

            # Parse results (filtering is now done at Redis level using TagField)
            documents = []
            for doc in results.docs:
                doc_dict = {
                    "text": doc.text,
                    "filename": doc.filename,
                    "source": doc.source,
                    "chunk_index": int(doc.chunk_index),
                    "group_id": getattr(doc, 'group_id', ''),
                    "score": float(doc.score)
                }
                documents.append(doc_dict)

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
            # Scan all doc:* keys (both numeric doc:N and UUID doc:xxxxx)
            for key in self.client.scan_iter(match="doc:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Exclude doc:hash:xxx keys used for duplicate tracking
                # Accept both numeric IDs (doc:0, doc:1) and UUID IDs (doc:abc123...)
                parts = key_str.split(':')
                if len(parts) != 2 or parts[0] != 'doc' or parts[1] == 'hash':
                    # Skip doc:hash:xxx or other invalid patterns
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
        Uses caching to avoid repeated scans of all documents.

        Args:
            filenames: List of filenames to count chunks for

        Returns:
            Dictionary mapping filename to chunk count
        """
        if not filenames:
            return {}

        try:
            # Try to get cached counts first (5 minute TTL)
            cache_key = "doc:counts:cache"
            cached_counts = self.client.get(cache_key)

            if cached_counts:
                # Use cached counts
                import json
                filename_counts = json.loads(cached_counts)
                logger.debug("Using cached document counts")
            else:
                # Cache miss - need to scan all documents
                logger.info("Cache miss - scanning all documents for counts")

                # Get all document keys efficiently using SCAN
                filename_counts = {}
                batch_size = 100
                key_batch = []

                for key in self.client.scan_iter(match="doc:*", count=batch_size):
                    key_str = key.decode('utf-8')

                    # Exclude doc:hash:xxx and doc:group:xxx keys, accept both numeric and UUID document IDs
                    parts = key_str.split(':')
                    if len(parts) != 2 or parts[0] != 'doc':
                        continue

                    key_batch.append(key)

                    # Process batch when it reaches batch_size
                    if len(key_batch) >= batch_size:
                        self._count_all_filenames_in_batch(key_batch, filename_counts)
                        key_batch = []

                # Process remaining keys
                if key_batch:
                    self._count_all_filenames_in_batch(key_batch, filename_counts)

                # Cache the counts for 5 minutes (300 seconds)
                import json
                self.client.setex(cache_key, 300, json.dumps(filename_counts))
                logger.info(f"Cached counts for {len(filename_counts)} unique filenames")

            # Build result with requested filenames
            result = {filename: filename_counts.get(filename, 0) for filename in filenames}
            return result

        except Exception as e:
            logger.error(f"Failed to batch count documents: {e}")
            # Return zero counts for all filenames on error
            return {filename: 0 for filename in filenames}

    def clear_document_count_cache(self):
        """
        Clear the cached document counts
        Should be called when documents are added, updated, or deleted
        """
        try:
            cache_key = "doc:counts:cache"
            self.client.delete(cache_key)
            logger.debug("Cleared document count cache")
        except Exception as e:
            logger.error(f"Failed to clear document count cache: {e}")

    def _count_all_filenames_in_batch(self, keys: List[bytes], filename_counts: Dict[str, int]):
        """
        Count occurrences of ALL filenames in a batch of keys (for caching)

        Args:
            keys: List of Redis keys to process
            filename_counts: Dictionary to update with counts
        """
        if not keys:
            return

        # Use pipeline to batch all operations
        pipe = self.client.pipeline()
        for key in keys:
            pipe.hget(key, 'filename')
        results = pipe.execute()

        # Count all filenames
        for filename_bytes in results:
            if filename_bytes:
                filename = filename_bytes.decode('utf-8')
                filename_counts[filename] = filename_counts.get(filename, 0) + 1

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
        Get all chunks for a specific filename by scanning all documents

        Due to RedisSearch limitations with special characters in filenames,
        we scan all doc:* keys and filter by filename in Python.

        Args:
            filename: Name of the file to get chunks for

        Returns:
            List of chunks with their text and metadata, sorted by chunk_index
        """
        try:
            chunks = []
            batch_size = 100
            key_batch = []

            # Scan all document keys
            for key in self.client.scan_iter(match="doc:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Skip non-document keys (like doc:hash:xxx)
                parts = key_str.split(':')
                if len(parts) != 2 or parts[0] != 'doc' or parts[1] == 'hash':
                    continue

                key_batch.append(key)

                # Process batch
                if len(key_batch) >= batch_size:
                    self._extract_chunks_from_batch(key_batch, filename, chunks)
                    key_batch = []

            # Process remaining keys
            if key_batch:
                self._extract_chunks_from_batch(key_batch, filename, chunks)

            # Sort chunks by chunk_index
            chunks.sort(key=lambda x: x['chunk_index'])

            logger.info(f"Retrieved {len(chunks)} chunks for {filename}")
            return chunks

        except Exception as e:
            logger.error(f"Failed to get chunks for {filename}: {e}")
            return []

    def _extract_chunks_from_batch(self, keys: List[bytes], target_filename: str, chunks: List[Dict]):
        """
        Extract chunks from a batch of keys that match the target filename

        Args:
            keys: List of Redis keys to process
            target_filename: Filename to match
            chunks: List to append matching chunks to
        """
        if not keys:
            return

        # Use pipeline to batch all operations
        pipe = self.client.pipeline()
        for key in keys:
            pipe.hgetall(key)
        results = pipe.execute()

        # Filter and extract chunks
        for key, doc_data in zip(keys, results):
            if not doc_data:
                continue

            # Decode document data
            doc = {k.decode('utf-8'): v.decode('utf-8') if isinstance(v, bytes) else v
                   for k, v in doc_data.items() if k != b'embedding'}

            # Check if filename matches
            if doc.get('filename') == target_filename:
                chunk_data = {
                    "text": doc.get("text", ""),
                    "filename": doc.get("filename", target_filename),
                    "source": doc.get("source", ""),
                    "chunk_index": int(doc.get("chunk_index", 0)),
                    "page": doc.get("source", "N/A"),
                    "metadata": {
                        "chunk_index": int(doc.get("chunk_index", 0)),
                        "source": doc.get("source", "")
                    }
                }
                chunks.append(chunk_data)

    def delete_by_filename(self, filename: str) -> int:
        """
        Delete all chunks associated with a filename by scanning

        Args:
            filename: Name of the file whose chunks should be deleted

        Returns:
            Number of chunks deleted
        """
        try:
            deleted_keys = []
            batch_size = 100
            key_batch = []

            # Scan all document keys
            for key in self.client.scan_iter(match="doc:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Skip non-document keys
                parts = key_str.split(':')
                if len(parts) != 2 or parts[0] != 'doc' or parts[1] == 'hash':
                    continue

                key_batch.append(key)

                # Process batch
                if len(key_batch) >= batch_size:
                    self._find_keys_to_delete(key_batch, filename, deleted_keys)
                    key_batch = []

            # Process remaining keys
            if key_batch:
                self._find_keys_to_delete(key_batch, filename, deleted_keys)

            # Delete all matching keys
            if deleted_keys:
                pipe = self.client.pipeline()
                for key in deleted_keys:
                    pipe.delete(key)
                pipe.execute()
                logger.info(f"Deleted {len(deleted_keys)} chunks for {filename}")

            return len(deleted_keys)
        except Exception as e:
            logger.error(f"Failed to delete documents for {filename}: {e}")
            return 0

    def _find_keys_to_delete(self, keys: List[bytes], target_filename: str, deleted_keys: List[bytes]):
        """
        Find keys in batch that match the target filename

        Args:
            keys: List of Redis keys to check
            target_filename: Filename to match
            deleted_keys: List to append matching keys to
        """
        if not keys:
            return

        # Use pipeline to batch all operations
        pipe = self.client.pipeline()
        for key in keys:
            pipe.hget(key, 'filename')
        results = pipe.execute()

        # Find matching keys
        for key, filename_bytes in zip(keys, results):
            if filename_bytes and filename_bytes.decode('utf-8') == target_filename:
                deleted_keys.append(key)

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
