#!/bin/bash

echo "Don't run this unless you set the sourceDB, targetDB and restore-date"
exit 1

aws dynamodb restore-table-to-point-in-time \
    --source-table-name FBP-Users \
    --target-table-name FBP-Users-OneWeekAgo \
    --restore-date-time 2026-07-11T12:00:00.000Z \
    --region us-east-1

