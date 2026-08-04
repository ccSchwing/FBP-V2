#!/bin/bash

set -e

echo "Restore FBP-Users to yesterday's data, delete the original table and then move the restored data to FBP-Users"

yesterday=$(date -u -v-1d +"%Y-%m-%dT00:00:00.000Z")

# 1. Restore to yesterday
aws dynamodb restore-table-to-point-in-time \
    --source-table-name FBP-Users \
    --target-table-name FBP-Users-Yesterday \
    --restore-date-time $yesterday \
    --region us-east-1

# 2. Wait for restore to complete
aws dynamodb describe-table --table-name FBP-Users-Yesterday --region us-east-1

# 3. Delete original table
aws dynamodb delete-table --table-name FBP-Users --region us-east-1

# 4. Wait for deletion to complete (table name becomes available)
aws dynamodb describe-table --table-name FBP-Users --region us-east-1
# Should return ResourceNotFoundException when fully deleted

# 5. Restore again with original name
aws dynamodb restore-table-to-point-in-time \
    --source-table-name FBP-Users-Yesterday \
    --target-table-name FBP-Users \
    --restore-date-time 2026-07-18T12:00:00.000Z \
    --region us-east-1

# 6. Clean up temporary table
aws dynamodb delete-table --table-name FBP-Users-Yesterday --region us-east-1

