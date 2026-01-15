#!/usr/bin/env python3
"""
Migration script to add document grouping support

This script:
1. Creates a default "uncategorized" group
2. Adds group_id field to all existing documents
3. Creates group:docs and doc:group indices
4. Recreates vector index with group_id TagField
"""

import sys
import os
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

import redis
from loguru import logger
from group_manager import GroupManager


class GroupMigration:
    """Handles migration to add document grouping support"""

    def __init__(self, redis_host='localhost', redis_port=6379):
        """
        Initialize migration

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
        """
        self.client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=0,
            decode_responses=False
        )
        self.group_manager = GroupManager(self.client)

    def run(self, dry_run=False):
        """
        Execute full migration

        Args:
            dry_run: If True, only shows what would be done without making changes

        Returns:
            Dictionary with migration statistics
        """
        logger.info("=" * 70)
        logger.info("Starting Document Grouping Migration")
        logger.info("=" * 70)

        if dry_run:
            logger.warning("DRY RUN MODE - No changes will be made")

        stats = {
            'default_group_id': None,
            'migrated_documents': 0,
            'unique_files': 0,
            'index_recreated': False
        }

        try:
            # Step 1: Ensure default group exists
            logger.info("\n[Step 1/5] Ensuring default group exists...")
            default_group_id = self.group_manager.get_default_group_id()
            stats['default_group_id'] = default_group_id
            logger.success(f"✓ Default group ID: {default_group_id}")

            # Step 2: Collect all document keys
            logger.info("\n[Step 2/5] Collecting document keys...")
            doc_keys = self._collect_document_keys()
            logger.info(f"Found {len(doc_keys)} document chunks")

            # Step 3: Migrate existing documents
            logger.info("\n[Step 3/5] Migrating documents to default group...")
            if not dry_run:
                migrated_count, unique_files = self._migrate_documents(doc_keys, default_group_id)
                stats['migrated_documents'] = migrated_count
                stats['unique_files'] = unique_files
                logger.success(f"✓ Migrated {migrated_count} chunks from {unique_files} unique files")
            else:
                logger.info(f"Would migrate {len(doc_keys)} chunks")

            # Step 4: Sync document counts
            logger.info("\n[Step 4/5] Syncing document counts...")
            if not dry_run:
                self.group_manager.sync_document_counts()
                logger.success("✓ Document counts synced")
            else:
                logger.info("Would sync document counts")

            # Step 5: Recreate vector index with group_id field
            logger.info("\n[Step 5/5] Recreating vector index...")
            if not dry_run:
                self._recreate_vector_index()
                stats['index_recreated'] = True
                logger.success("✓ Vector index recreated with group_id field")
            else:
                logger.info("Would recreate vector index")

            # Summary
            logger.info("\n" + "=" * 70)
            logger.info("Migration Summary:")
            logger.info("=" * 70)
            logger.info(f"Default Group ID:     {stats['default_group_id']}")
            logger.info(f"Migrated Chunks:      {stats['migrated_documents']}")
            logger.info(f"Unique Files:         {stats['unique_files']}")
            logger.info(f"Index Recreated:      {stats['index_recreated']}")
            logger.info("=" * 70)

            if dry_run:
                logger.warning("\nDRY RUN completed - No changes were made")
            else:
                logger.success("\n✓ Migration completed successfully!")

            return stats

        except Exception as e:
            logger.error(f"\n✗ Migration failed: {e}")
            raise

    def _collect_document_keys(self):
        """
        Collect all document keys from Redis

        Returns:
            List of document key bytes
        """
        doc_keys = []

        for key in self.client.scan_iter(match="doc:*", count=100):
            key_str = key.decode('utf-8')

            # Skip special keys
            parts = key_str.split(':')
            if len(parts) == 2 and parts[0] == 'doc' and parts[1] not in ['hash', 'group', 'default']:
                # Check if it's a hash (document chunk)
                key_type = self.client.type(key)
                if key_type == b'hash':
                    doc_keys.append(key)

        return doc_keys

    def _migrate_documents(self, doc_keys, default_group_id):
        """
        Add group_id to all documents and create indices

        Args:
            doc_keys: List of document keys
            default_group_id: Default group ID to assign

        Returns:
            Tuple of (migrated_count, unique_files_count)
        """
        filenames = set()
        migrated_count = 0
        batch_size = 100

        # Process in batches
        for i in range(0, len(doc_keys), batch_size):
            batch = doc_keys[i:i + batch_size]

            pipe = self.client.pipeline()

            for key in batch:
                # Add group_id field to document
                pipe.hset(key, 'group_id', default_group_id)
                # Get filename for indexing
                pipe.hget(key, 'filename')

            results = pipe.execute()

            # Collect unique filenames (every other result is filename)
            for j in range(1, len(results), 2):
                if results[j]:
                    filenames.add(results[j].decode('utf-8'))

            migrated_count += len(batch)

            # Progress indicator
            if (i + batch_size) % 1000 == 0:
                logger.info(f"  Progress: {migrated_count}/{len(doc_keys)} chunks...")

        # Create group indices
        if filenames:
            logger.info(f"Creating group indices for {len(filenames)} files...")

            # Create group:docs set
            self.client.sadd(f'group:docs:{default_group_id}', *filenames)

            # Create doc:group reverse index
            pipe = self.client.pipeline()
            for filename in filenames:
                pipe.set(f'doc:group:{filename}', default_group_id)
            pipe.execute()

        return migrated_count, len(filenames)

    def _recreate_vector_index(self):
        """Recreate vector index with group_id field"""
        from redis.commands.search.field import TextField, VectorField, NumericField, TagField
        from redis.commands.search.indexDefinition import IndexDefinition, IndexType

        index_name = 'pdf_index'

        try:
            # Drop existing index (keep documents)
            logger.info("  Dropping existing index...")
            self.client.ft(index_name).dropindex(delete_documents=False)
            logger.info("  ✓ Index dropped")
        except Exception as e:
            logger.warning(f"  Index doesn't exist or couldn't be dropped: {e}")

        # Create new index with group_id field
        logger.info("  Creating new index with group_id field...")

        schema = (
            TextField("text"),
            TextField("filename", sortable=True),
            TextField("source"),
            NumericField("chunk_index"),
            TagField("group_id", separator="|"),  # NEW: Support OR search across groups
            VectorField(
                "embedding",
                "FLAT",
                {
                    "TYPE": "FLOAT32",
                    "DIM": 1024,  # KURE-v1 embedding dimension
                    "DISTANCE_METRIC": "COSINE",
                }
            ),
        )

        definition = IndexDefinition(
            prefix=["doc:"],
            index_type=IndexType.HASH
        )

        self.client.ft(index_name).create_index(
            fields=schema,
            definition=definition
        )

        logger.info("  ✓ New index created")

    def verify_migration(self):
        """
        Verify migration was successful

        Returns:
            Boolean indicating if migration is valid
        """
        logger.info("\nVerifying migration...")

        # Check default group exists
        default_group_id = self.client.get('group:default')
        if not default_group_id:
            logger.error("✗ Default group not found")
            return False

        default_group_id = default_group_id.decode('utf-8')
        logger.info(f"✓ Default group exists: {default_group_id}")

        # Check group metadata
        group_data = self.client.hgetall(f'group:{default_group_id}')
        if not group_data:
            logger.error("✗ Group metadata not found")
            return False

        logger.info(f"✓ Group metadata exists")

        # Sample check: verify some documents have group_id
        sample_keys = []
        for i, key in enumerate(self.client.scan_iter(match="doc:*", count=10)):
            key_str = key.decode('utf-8')
            parts = key_str.split(':')
            if len(parts) == 2 and parts[0] == 'doc' and parts[1] not in ['hash', 'group', 'default']:
                sample_keys.append(key)
                if len(sample_keys) >= 5:
                    break

        if sample_keys:
            logger.info(f"Checking {len(sample_keys)} sample documents...")
            for key in sample_keys:
                group_id = self.client.hget(key, 'group_id')
                if not group_id:
                    logger.error(f"✗ Document {key.decode('utf-8')} missing group_id")
                    return False

            logger.info(f"✓ Sample documents have group_id field")

        # Check index exists
        try:
            index_info = self.client.ft('pdf_index').info()
            logger.info(f"✓ Vector index exists with {index_info.get('num_docs', 0)} documents")
        except Exception as e:
            logger.error(f"✗ Vector index check failed: {e}")
            return False

        logger.success("\n✓ Migration verification passed!")
        return True


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Migrate database to support document grouping')
    parser.add_argument('--host', default='localhost', help='Redis host (default: localhost)')
    parser.add_argument('--port', type=int, default=6379, help='Redis port (default: 6379)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--verify', action='store_true', help='Verify existing migration')

    args = parser.parse_args()

    migration = GroupMigration(redis_host=args.host, redis_port=args.port)

    if args.verify:
        # Verify only
        success = migration.verify_migration()
        sys.exit(0 if success else 1)
    else:
        # Run migration
        try:
            stats = migration.run(dry_run=args.dry_run)

            if not args.dry_run:
                # Verify after migration
                logger.info("\n" + "=" * 70)
                success = migration.verify_migration()
                logger.info("=" * 70)
                sys.exit(0 if success else 1)
            else:
                sys.exit(0)

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == '__main__':
    main()
