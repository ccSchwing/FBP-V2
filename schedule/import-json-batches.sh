#!/bin/bash

for file in batch_*.json; do
    echo "Importing $file..."
    aws --region us-east-1 dynamodb batch-write-item --request-items file://"$file"
    sleep 1
done