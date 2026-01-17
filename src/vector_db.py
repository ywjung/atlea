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
from .performance_utils import log_slow_query


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
        Initialize Redis Vector Database with dual index support (Blue-Green deployment)

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            index_name: Base name for search index (actual name will be versioned)
            embedding_dim: Dimension of embeddings
            max_connections: Maximum number of connections in pool
            socket_timeout: Socket timeout in seconds
            socket_keepalive: Enable TCP keepalive
            socket_keepalive_options: TCP keepalive options dict
            health_check_interval: Connection health check interval in seconds
        """
        self.base_index_name = index_name  # Base name for versioned indexes
        self.embedding_dim = embedding_dim

        try:
            # Create simple connection pool (disable health_check for faster startup)
            pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                max_connections=max_connections,
                decode_responses=False,  # Keep as bytes for compatibility with existing code
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

        # Initialize active index tracking
        self._initialize_active_index()

    def _initialize_active_index(self):
        """Initialize or restore active index tracking"""
        active_index = self.client.get("index:active")

        if active_index:
            # Restore existing active index
            self.index_name = active_index.decode('utf-8')
            logger.info(f"Restored active index: {self.index_name}")
        else:
            # First time initialization - create versioned index
            import time
            version = int(time.time())
            self.index_name = f"{self.base_index_name}_v{version}"
            self.client.set("index:active", self.index_name)
            logger.info(f"Initialized new active index: {self.index_name}")

        # Create or verify the active index exists
        self._create_index()

    @property
    def active_index_name(self) -> str:
        """Get the currently active index name"""
        active = self.client.get("index:active")
        if active:
            return active.decode('utf-8')
        return self.index_name  # Fallback to current

    def create_new_index(self, index_name: str) -> bool:
        """
        Create a new index with the specified name for dual index system

        Args:
            index_name: Name for the new index

        Returns:
            True if created successfully, False otherwise
        """
        try:
            logger.info(f"Creating new index: {index_name}")
            schema = (
                TextField("text"),
                TextField("filename", sortable=True),
                TagField("filename_exact", separator="|"),
                TagField("filename_hash", separator="|"),
                TextField("source"),
                NumericField("chunk_index"),
                TagField("group_id", separator="|"),
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
                prefix=[f"doc:{index_name}:"],  # Unique prefix for this index
                index_type=IndexType.HASH
            )

            self.client.ft(index_name).create_index(
                fields=schema,
                definition=definition
            )
            logger.success(f"Index '{index_name}' created successfully")
            return True
        except Exception as e:
            # RediSearch 모듈이 없는 경우 경고만 하고 성공으로 처리
            if "unknown command 'FT.CREATE'" in str(e):
                logger.warning(f"⚠️  RediSearch module not available - skipping index '{index_name}' creation")
                logger.warning(f"⚠️  Vector search disabled - system will work without search features")
                return True  # Return True to allow system to continue
            # 인덱스가 이미 존재하는 경우
            elif "Index already exists" in str(e):
                logger.info(f"Index '{index_name}' already exists")
                return True
            else:
                logger.error(f"Failed to create index '{index_name}': {e}")
                return False

    def swap_indexes(self, new_index_name: str) -> bool:
        """
        Atomically swap the active index (Blue-Green deployment)

        Args:
            new_index_name: Name of the new index to make active

        Returns:
            True if swap successful, False otherwise
        """
        try:
            old_index_name = self.active_index_name

            # Verify new index exists (skip if RediSearch not available)
            try:
                self.client.ft(new_index_name).info()
                logger.info(f"✓ Verified new index '{new_index_name}' exists")
            except Exception as e:
                # RediSearch 모듈이 없는 경우 검증을 건너뛰고 계속 진행
                if "unknown command 'FT.INFO'" in str(e):
                    logger.warning(f"⚠️  RediSearch not available - skipping index verification")
                else:
                    logger.error(f"Cannot swap: new index '{new_index_name}' verification failed: {e}")
                    return False

            # Atomic swap
            self.client.set("index:active", new_index_name)
            self.index_name = new_index_name

            logger.success(f"✅ Index swap complete: {old_index_name} → {new_index_name}")

            # Schedule old index cleanup (after a grace period)
            self.client.set(f"index:old:{old_index_name}", "1", ex=300)  # Mark for cleanup in 5 minutes

            return True
        except Exception as e:
            logger.error(f"Failed to swap indexes: {e}")
            return False

    def cleanup_old_index(self, index_name: str) -> bool:
        """
        Clean up old index and its documents after swap

        Args:
            index_name: Name of old index to cleanup

        Returns:
            True if cleanup successful, False otherwise
        """
        try:
            logger.info(f"Cleaning up old index: {index_name}")

            # Delete all documents with this index prefix
            cursor = '0'
            count = 0
            while True:
                cursor, keys = self.client.scan(
                    cursor=cursor,
                    match=f"doc:{index_name}:*",
                    count=100
                )
                if keys:
                    self.client.delete(*keys)
                    count += len(keys)
                if cursor == 0 or cursor == b'0':
                    break

            # Drop the index
            try:
                self.client.ft(index_name).dropindex(delete_documents=True)
                logger.info(f"Dropped index: {index_name}")
            except Exception:
                pass  # Index might not exist

            logger.success(f"Cleaned up {count} documents from old index '{index_name}'")
            return True
        except Exception as e:
            logger.error(f"Failed to cleanup old index '{index_name}': {e}")
            return False

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
                # RediSearch 모듈이 없는 경우 경고만 하고 계속 진행
                if "unknown command 'FT.CREATE'" in str(e):
                    logger.warning(f"⚠️  RediSearch module not available - vector search disabled")
                    logger.warning(f"⚠️  Install Redis Stack to enable vector search features")
                    return
                # 인덱스가 이미 존재하는 경우
                elif "Index already exists" in str(e):
                    logger.info(f"Index '{self.index_name}' already exists")
                    return
                else:
                    logger.error(f"Failed to create index: {e}")
                    raise

    def add_documents(self, documents: List[Dict], embeddings: List[List[float]], target_index: Optional[str] = None):
        """
        Add documents with embeddings to database

        Args:
            documents: List of document dictionaries
            embeddings: List of embedding vectors
            target_index: Optional target index name (for dual index system). If None, uses active index.
        """
        if len(documents) != len(embeddings):
            raise ValueError("Number of documents must match number of embeddings")

        # Use specified index or active index
        index_name = target_index if target_index else self.active_index_name

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
            # Generate unique document ID with index-specific prefix
            doc_id = f"doc:{index_name}:{uuid.uuid4().hex}"

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
            # Add to filename index for O(1) lookup by filename
            filename_index_key = f"doc:files:{index_name}:{filename_hash}"
            pipe.sadd(filename_index_key, doc_id)

        pipe.execute()

        # Wait for Redis Search index to update
        # Redis Search indexing is asynchronous, so we need a small delay
        # to ensure newly added documents are searchable immediately
        import time
        time.sleep(0.2)  # 200ms delay for index propagation

        # Clear document count cache to reflect new documents
        self.clear_document_count_cache()

        logger.success(f"Added {len(documents)} documents to database")

    @log_slow_query(threshold_seconds=1.0)
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
            # 🆕 Early return if group_ids is an empty list (no groups = no results)
            if group_ids is not None and len(group_ids) == 0:
                logger.info("⚠️ Empty group_ids list - user has no accessible groups, returning no results")
                return []

            # 🆕 Early return if document_ids is an empty list (no documents = no results)
            if document_ids is not None and len(document_ids) == 0:
                logger.info("⚠️ Empty document_ids list - no documents to search, returning no results")
                return []

            # Convert query embedding to bytes
            query_bytes = np.array(query_embedding, dtype=np.float32).tobytes()

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

            query = (
                Query(base_query)
                .return_fields("text", "filename", "source", "chunk_index", "group_id", "score")
                .dialect(2)
            )

            # Execute search using execute_command (Query class has issues with hybrid queries)
            try:
                # Use active_index_name to query the currently active index
                index_name = self.active_index_name

                raw_results = self.client.execute_command(
                    'FT.SEARCH', index_name,
                    base_query,
                    'PARAMS', '2', 'vec', query_bytes,
                    'RETURN', '6', 'text', 'filename', 'source', 'chunk_index', 'group_id', 'score',
                    'DIALECT', '2'
                )

            except Exception as e:
                logger.error(f"Vector search execute_command failed: {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

            # Parse raw results
            num_results = raw_results[0]

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

            return documents
        except Exception as e:
            logger.error(f"Search failed: {e}")
            raise

    def count_documents(self) -> int:
        """Get total number of documents (chunks) in database"""
        try:
            # Try RediSearch first (most efficient)
            info = self.client.ft(self.active_index_name).info()
            return int(info.get("num_docs", 0))
        except Exception:
            # Fallback: Count keys manually if RediSearch is unavailable
            try:
                index_name = self.active_index_name
                cursor = 0
                count = 0

                while True:
                    cursor, keys = self.client.scan(cursor, match=f"doc:{index_name}:*", count=100)
                    # Filter out non-document keys
                    for key in keys:
                        key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                        # Skip metadata keys like doc:hash:, doc:group:, etc.
                        if not any(x in key_str for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
                            count += 1

                    if cursor == 0:
                        break

                return count
            except Exception as e:
                logger.warning(f"Failed to count documents: {e}")
                return 0

    def count_unique_files(self) -> int:
        """
        Get total number of unique PDF files (optimized with SCAN + pipeline)

        Performance improvements:
        - Uses SCAN instead of KEYS to avoid blocking Redis
        - Batches operations with pipeline to reduce round trips
        - Only fetches filename field instead of entire document
        - Scans only the active index
        """
        try:
            filenames = set()
            batch_size = 100  # Process keys in batches
            key_batch = []

            # Get active index name
            index_name = self.active_index_name

            # Use SCAN to iterate keys without blocking Redis
            # Scan only the active index: doc:index_name:*
            for key in self.client.scan_iter(match=f"doc:{index_name}:*", count=batch_size):
                key_str = key.decode('utf-8')

                # Skip non-document keys (like doc:index_name:hash:xxx, doc:index_name:group:xxx, etc.)
                parts = key_str.split(':')
                if len(parts) < 3:
                    continue
                # Skip metadata keys
                if any(x in key_str for x in [':hash:', ':group:', ':version:', ':counts:', ':files']):
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
        except Exception:
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
            else:
                # Cache miss - need to scan all documents
                logger.info("Cache miss - scanning all documents for counts")

                # Get all document keys efficiently using SCAN (filtered by active index)
                filename_counts = {}
                batch_size = 100
                key_batch = []

                # Use active index for more efficient scanning
                index_pattern = f"doc:{self.active_index_name}:*"

                for key in self.client.scan_iter(match=index_pattern, count=batch_size):
                    key_str = key.decode('utf-8')

                    # Exclude doc:hash:xxx and doc:group:xxx keys, accept both numeric and UUID document IDs
                    parts = key_str.split(':')
                    # Accept doc:id or doc:index:id formats, exclude doc:hash:xxx, doc:group:xxx, doc:version:xxx, doc:counts:xxx, doc:files
                    if len(parts) < 2 or parts[0] != 'doc' or parts[1] in ['hash', 'group', 'counts', 'version', 'files']:
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
        Get all chunks for a specific filename using filename index for O(1) lookup.

        Uses the filename index (doc:files:{index}:{hash}) for direct key lookup
        instead of scanning all documents. Falls back to scan if index doesn't exist.

        Args:
            filename: Name of the file to get chunks for

        Returns:
            List of chunks with their text and metadata, sorted by chunk_index
        """
        try:
            # Calculate filename hash for index lookup
            filename_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()
            filename_index_key = f"doc:files:{self.active_index_name}:{filename_hash}"

            # Try to get doc_ids from filename index (O(1) lookup)
            doc_ids = self.client.smembers(filename_index_key)

            if doc_ids:
                # Use index-based retrieval (optimized path)
                chunks = self._get_chunks_from_index(doc_ids, filename)
                logger.info(f"Retrieved {len(chunks)} chunks for {filename} (indexed)")
                return chunks

            # Fallback to scan for backward compatibility (when index doesn't exist)
            logger.debug(f"Filename index not found for {filename}, falling back to scan")
            chunks = self._get_chunks_by_scan(filename)
            logger.info(f"Retrieved {len(chunks)} chunks for {filename} (scanned)")
            return chunks

        except Exception as e:
            logger.error(f"Failed to get chunks for {filename}: {e}")
            return []

    def _get_chunks_from_index(self, doc_ids: set, filename: str) -> List[Dict]:
        """
        Get chunks using doc_ids from filename index with Pipeline.

        Args:
            doc_ids: Set of document IDs from filename index
            filename: Original filename for verification

        Returns:
            List of chunks sorted by chunk_index
        """
        if not doc_ids:
            return []

        chunks = []
        doc_id_list = list(doc_ids)

        # Batch fetch all documents using pipeline (single round trip)
        pipe = self.client.pipeline()
        for doc_id in doc_id_list:
            # Decode if bytes
            doc_id_str = doc_id.decode('utf-8') if isinstance(doc_id, bytes) else doc_id
            pipe.hgetall(doc_id_str)
        results = pipe.execute()

        # Extract chunk data
        for doc_data in results:
            if not doc_data:
                continue

            # Decode document data (exclude embedding for performance)
            doc = {k.decode('utf-8'): v.decode('utf-8') if isinstance(v, bytes) else v
                   for k, v in doc_data.items() if k != b'embedding'}

            # Verify filename matches (safety check)
            if doc.get('filename') == filename:
                chunk_data = {
                    "text": doc.get("text", ""),
                    "filename": doc.get("filename", filename),
                    "source": doc.get("source", ""),
                    "chunk_index": int(doc.get("chunk_index", 0)),
                    "page": doc.get("source", "N/A"),
                    "metadata": {
                        "chunk_index": int(doc.get("chunk_index", 0)),
                        "source": doc.get("source", "")
                    }
                }
                chunks.append(chunk_data)

        # Sort by chunk_index
        chunks.sort(key=lambda x: x['chunk_index'])
        return chunks

    def _get_chunks_by_scan(self, filename: str) -> List[Dict]:
        """
        Fallback method: Get chunks by scanning all documents (for backward compatibility).

        Args:
            filename: Name of the file to get chunks for

        Returns:
            List of chunks sorted by chunk_index
        """
        chunks = []
        batch_size = 100
        key_batch = []

        # Scan document keys from active index
        index_pattern = f"doc:{self.active_index_name}:*"

        for key in self.client.scan_iter(match=index_pattern, count=batch_size):
            key_str = key.decode('utf-8')

            # Skip non-document keys
            parts = key_str.split(':')
            if parts[0] != 'doc' or len(parts) < 2:
                continue
            if parts[1] in ['hash', 'group', 'version', 'counts', 'files']:
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
        return chunks

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
        Delete all chunks associated with a filename using filename index for O(1) lookup.

        Uses the filename index (doc:files:{index}:{hash}) for direct key lookup
        instead of scanning all documents. Falls back to scan if index doesn't exist.

        Args:
            filename: Name of the file whose chunks should be deleted

        Returns:
            Number of chunks deleted
        """
        try:
            # Calculate filename hash for index lookup
            filename_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()
            filename_index_key = f"doc:files:{self.active_index_name}:{filename_hash}"

            # Try to get doc_ids from filename index (O(1) lookup)
            doc_ids = self.client.smembers(filename_index_key)

            if doc_ids:
                # Use index-based deletion (optimized path)
                deleted_count = self._delete_by_index(doc_ids, filename_index_key)
                logger.info(f"Deleted {deleted_count} chunks for {filename} (indexed)")
                return deleted_count

            # Fallback to scan for backward compatibility
            logger.debug(f"Filename index not found for {filename}, falling back to scan")
            deleted_count = self._delete_by_scan(filename)
            logger.info(f"Deleted {deleted_count} chunks for {filename} (scanned)")
            return deleted_count

        except Exception as e:
            logger.error(f"Failed to delete documents for {filename}: {e}")
            return 0

    def _delete_by_index(self, doc_ids: set, filename_index_key: str) -> int:
        """
        Delete chunks using doc_ids from filename index with Pipeline.

        Args:
            doc_ids: Set of document IDs from filename index
            filename_index_key: Key of the filename index to delete

        Returns:
            Number of chunks deleted
        """
        if not doc_ids:
            return 0

        # Delete all documents and the index in a single pipeline
        pipe = self.client.pipeline()
        for doc_id in doc_ids:
            doc_id_str = doc_id.decode('utf-8') if isinstance(doc_id, bytes) else doc_id
            pipe.delete(doc_id_str)
        # Also delete the filename index itself
        pipe.delete(filename_index_key)
        pipe.execute()

        # Clear document count cache after deletion
        self.clear_document_count_cache()

        return len(doc_ids)

    def _delete_by_scan(self, filename: str) -> int:
        """
        Fallback method: Delete chunks by scanning all documents (for backward compatibility).

        Args:
            filename: Name of the file whose chunks should be deleted

        Returns:
            Number of chunks deleted
        """
        deleted_keys = []
        batch_size = 100
        key_batch = []

        # Scan document keys from active index
        index_pattern = f"doc:{self.active_index_name}:*"

        for key in self.client.scan_iter(match=index_pattern, count=batch_size):
            key_str = key.decode('utf-8')

            # Skip non-document keys
            parts = key_str.split(':')
            if len(parts) < 2 or parts[0] != 'doc' or parts[1] in ['hash', 'group', 'counts', 'version', 'files']:
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

            # Clear document count cache after deletion
            self.clear_document_count_cache()

        return len(deleted_keys)

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

    def build_filename_index(self) -> Dict[str, int]:
        """
        Build filename index for existing documents (migration utility).

        Scans all documents and creates the filename index (doc:files:{index}:{hash})
        for O(1) lookup. This is a one-time migration that enables optimized
        chunk retrieval and deletion.

        Returns:
            Dictionary with {filename: chunk_count} for indexed files
        """
        try:
            logger.info("Building filename index for existing documents...")
            batch_size = 100
            key_batch = []
            filename_counts = {}

            # Scan document keys from active index
            index_pattern = f"doc:{self.active_index_name}:*"

            for key in self.client.scan_iter(match=index_pattern, count=batch_size):
                key_str = key.decode('utf-8')

                # Skip non-document keys
                parts = key_str.split(':')
                if parts[0] != 'doc' or len(parts) < 2:
                    continue
                if parts[1] in ['hash', 'group', 'version', 'counts', 'files']:
                    continue

                key_batch.append(key)

                # Process batch
                if len(key_batch) >= batch_size:
                    self._build_index_batch(key_batch, filename_counts)
                    key_batch = []

            # Process remaining keys
            if key_batch:
                self._build_index_batch(key_batch, filename_counts)

            logger.success(f"Built filename index for {len(filename_counts)} files, total {sum(filename_counts.values())} chunks")
            return filename_counts

        except Exception as e:
            logger.error(f"Failed to build filename index: {e}")
            return {}

    def _build_index_batch(self, keys: List[bytes], filename_counts: Dict[str, int]):
        """
        Build filename index entries for a batch of document keys.

        Args:
            keys: List of Redis keys to process
            filename_counts: Dictionary to track counts per filename
        """
        if not keys:
            return

        # Get filenames for all keys in batch
        pipe = self.client.pipeline()
        for key in keys:
            pipe.hget(key, 'filename')
        results = pipe.execute()

        # Group by filename hash for batch index updates
        filename_to_keys = {}
        for key, filename_bytes in zip(keys, results):
            if not filename_bytes:
                continue

            filename = filename_bytes.decode('utf-8') if isinstance(filename_bytes, bytes) else filename_bytes
            filename_hash = hashlib.md5(filename.encode('utf-8')).hexdigest()

            if filename_hash not in filename_to_keys:
                filename_to_keys[filename_hash] = []
            filename_to_keys[filename_hash].append(key)

            # Track counts
            filename_counts[filename] = filename_counts.get(filename, 0) + 1

        # Add all keys to their respective filename index sets
        pipe = self.client.pipeline()
        for filename_hash, doc_keys in filename_to_keys.items():
            index_key = f"doc:files:{self.active_index_name}:{filename_hash}"
            for key in doc_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                pipe.sadd(index_key, key_str)
        pipe.execute()

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

    def bm25_search(
        self,
        query_text: str,
        top_k: int = 20,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        BM25 full-text search using TextField

        Args:
            query_text: Query text for BM25 search
            top_k: Number of results to return
            group_ids: Optional list of group IDs to filter by
            document_ids: Optional list of document filenames to filter by

        Returns:
            List of matching documents with BM25 scores
        """
        try:
            # 🆕 Early return if group_ids is an empty list (no groups = no results)
            if group_ids is not None and len(group_ids) == 0:
                logger.info("⚠️ Empty group_ids list - user has no accessible groups, returning no results")
                return []

            # 🆕 Early return if document_ids is an empty list (no documents = no results)
            if document_ids is not None and len(document_ids) == 0:
                logger.info("⚠️ Empty document_ids list - no documents to search, returning no results")
                return []

            # Build filters
            filters = []

            # Group filter
            if group_ids:
                escaped_groups = [self.escape_tag_value(gid) for gid in group_ids]
                group_filter = "|".join(escaped_groups)
                filters.append(f"@group_id:{{{group_filter}}}")

            # Document filter
            if document_ids:
                filename_hashes = [hashlib.md5(filename.encode('utf-8')).hexdigest() for filename in document_ids]
                hash_filter = "|".join(filename_hashes)
                filters.append(f"@filename_hash:{{{hash_filter}}}")

            # Escape query text for TextField search
            escaped_query = self.escape_redis_query(query_text)

            # Build BM25 query
            # Search in 'text' TextField with BM25 scoring
            text_query = f'@text:"{escaped_query}"'

            # Combine with filters
            if filters:
                if len(filters) == 1:
                    combined_filter = filters[0]
                else:
                    combined_filter = "(" + " ".join(filters) + ")"
                final_query = f"({combined_filter} {text_query})"
            else:
                final_query = text_query

            # Execute BM25 search
            query = (
                Query(final_query)
                .return_fields("text", "filename", "source", "chunk_index", "group_id")
                .paging(0, top_k)
                .dialect(2)
            )

            # Use active_index_name to query the currently active index
            results = self.client.ft(self.active_index_name).search(query)

            # Parse results
            documents = []
            for i, doc in enumerate(results.docs):
                # BM25 score is implicit in ranking order
                # Use inverse rank as score (higher rank = higher score)
                bm25_score = 1.0 / (i + 1)

                doc_dict = {
                    "text": doc.text,
                    "filename": doc.filename,
                    "source": getattr(doc, 'source', ''),
                    "chunk_index": int(getattr(doc, 'chunk_index', 0)),
                    "group_id": getattr(doc, 'group_id', ''),
                    "score": bm25_score,
                    "rank": i + 1
                }
                documents.append(doc_dict)

            return documents

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    @staticmethod
    def _reciprocal_rank_fusion(
        rankings: List[List[Dict]],
        k: int = 60
    ) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) algorithm to combine multiple rankings

        RRF formula: score = sum(1 / (k + rank_i))
        where rank_i is the rank in each ranking list

        Args:
            rankings: List of ranking lists (each is a list of documents)
            k: Constant for RRF formula (default: 60)

        Returns:
            Combined ranking list sorted by RRF score
        """
        # Track scores for each unique document
        doc_scores = {}
        doc_data = {}

        # Process each ranking
        for ranking in rankings:
            for rank, doc in enumerate(ranking, start=1):
                # Use document text as unique identifier
                doc_id = doc['text']

                # Calculate RRF contribution
                rrf_contribution = 1.0 / (k + rank)

                # Add to total score
                if doc_id in doc_scores:
                    doc_scores[doc_id] += rrf_contribution
                else:
                    doc_scores[doc_id] = rrf_contribution
                    doc_data[doc_id] = doc

        # Create final ranking sorted by RRF score
        final_ranking = []
        for doc_id, score in sorted(doc_scores.items(), key=lambda x: x[1], reverse=True):
            doc = doc_data[doc_id].copy()
            doc['score'] = score
            final_ranking.append(doc)

        return final_ranking

    def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        top_k: int = 5,
        group_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None,
        retrieval_k: int = 20
    ) -> List[Dict]:
        """
        Hybrid search combining vector search (semantic) and BM25 (keyword) using RRF

        Args:
            query_text: Query text for BM25 search
            query_embedding: Query embedding vector for semantic search
            top_k: Number of final results to return
            group_ids: Optional list of group IDs to filter by
            document_ids: Optional list of document filenames to filter by
            retrieval_k: Number of documents to retrieve from each method before fusion (default: 20)

        Returns:
            List of documents ranked by RRF score
        """
        try:
            logger.info(f"Hybrid search: query='{query_text[:50]}...', top_k={top_k}, retrieval_k={retrieval_k}")

            # 1. Vector search (semantic similarity)
            vector_results = self.search(
                query_embedding=query_embedding,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

            # 2. BM25 search (keyword matching)
            bm25_results = self.bm25_search(
                query_text=query_text,
                top_k=retrieval_k,
                group_ids=group_ids,
                document_ids=document_ids
            )

            # 3. Combine using Reciprocal Rank Fusion
            combined_results = self._reciprocal_rank_fusion([vector_results, bm25_results])

            # 4. Return top_k results
            final_results = combined_results[:top_k]
            logger.info(f"Hybrid search returned {len(final_results)} final results")

            return final_results

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            # Fallback to vector search only
            logger.warning("Falling back to vector search only")
            return self.search(
                query_embedding=query_embedding,
                top_k=top_k,
                group_ids=group_ids,
                document_ids=document_ids
            )
