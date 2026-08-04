#!/bin/bash


echo "DO NOT RUN THIS UNTIL YOU ARE READY FOR THE NEW NFL SEASON."
echo "YOU WILL NEED TO UPDATE THE --table-name FIRST.  EXITING NOW."

exit 0

aws dynamodb create-table \
    --table-name 2025-Schedule \
    --attribute-definitions \
        AttributeName=Week,AttributeType=N \
        AttributeName=GameId,AttributeType=S \
    --key-schema \
        AttributeName=Week,KeyType=HASH \
        AttributeName=GameId,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST
