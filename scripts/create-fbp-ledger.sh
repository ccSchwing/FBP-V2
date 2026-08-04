#!/bin/bash

# Using AWS CLI (or use the console)
aws dynamodb create-table \
    --table-name FBP-Payout-Ledger \
    --attribute-definitions \
        AttributeName=RecordType,AttributeType=S \
        AttributeName=Timestamp,AttributeType=S \
    --key-schema \
        AttributeName=RecordType,KeyType=HASH \
        AttributeName=Timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST

