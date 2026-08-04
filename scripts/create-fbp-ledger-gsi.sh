#!/bin/bash

# Add the GSI when ready
aws dynamodb update-table \
    --table-name FBP-Payout-Ledger \
    --attribute-definitions \
        AttributeName=WeekNumber,AttributeType=S \
        AttributeName=Timestamp,AttributeType=S \
    --global-secondary-index-updates \
        '[{
            "Create": {
                "IndexName": "WeekByDate-index",
                "KeySchema": [
                    {"AttributeName": "WeekNumber", "KeyType": "HASH"},
                    {"AttributeName": "Timestamp", "KeyType": "RANGE"}
                ],
                "Projection": {"ProjectionType": "ALL"},
                "BillingMode": "PAY_PER_REQUEST"
            }
        }]'

