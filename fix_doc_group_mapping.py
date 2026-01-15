#!/usr/bin/env python3
"""
Fix missing doc:group reverse mappings
Creates doc:group:{filename} → group_id mappings for all files in groups
"""

import redis

# Connect to Redis
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Get the default group ID
group_id = "48bf2a96-2381-40fc-ae2c-00d749b51081"

# Get all files in the group
filenames = redis_client.smembers(f"group:docs:{group_id}")

print(f"Found {len(filenames)} files in group {group_id}")
print("")

# Create reverse mappings
created = 0
for filename in filenames:
    # Check if mapping already exists
    existing = redis_client.get(f"doc:group:{filename}")

    if existing:
        print(f"  ⏭️  {filename} (already mapped to {existing})")
    else:
        # Create the reverse mapping
        redis_client.set(f"doc:group:{filename}", group_id)
        created += 1
        print(f"  ✅ {filename}")

print("")
print(f"✅ Created {created} reverse mappings")
print(f"📊 Total files: {len(filenames)}")
print("")

# Verify by counting total doc:group keys
total_mappings = len(list(redis_client.scan_iter("doc:group:*")))
print(f"Total doc:group:* keys in Redis: {total_mappings}")
