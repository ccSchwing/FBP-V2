#!/bin/bash

RESTORE_DATE=$(date -u -v -120M +"%Y-%m-%dT%H:%M:%SZ")

aws dynamodb restore-table-to-point-in-time \
    --source-table-name FBP-Users-OneWeekAgo \
    --target-table-name FBP-Users \
    --restore-date-time $RESTORE_DATE \
    --region us-east-1

