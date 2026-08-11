#!/bin/bash

TABLE_NAME="2026-FBP-Users"
REGION="us-east-1"  # Change to your region

echo "Starting reset of totalWins for all records in $TABLE_NAME..."

LAST_KEY=""

while true; do
  # Build the scan command (with or without pagination token)
  if [ -z "$LAST_KEY" ]; then
    RESULT=$(aws dynamodb scan \
      --table-name "$TABLE_NAME" \
      --region "$REGION" \
      --projection-expression "email" \
      --output json)
  else
    RESULT=$(aws dynamodb scan \
      --table-name "$TABLE_NAME" \
      --region "$REGION" \
      --projection-expression "email" \
      --exclusive-start-key "$LAST_KEY" \
      --output json)
  fi

  # Extract items and update each one
  ITEMS=$(echo "$RESULT" | jq -c '.Items[]')

  while IFS= read -r ITEM; do
    USER_ID=$(echo "$ITEM" | jq -r '.email.S')

    aws dynamodb update-item \
      --table-name "$TABLE_NAME" \
      --region "$REGION" \
      --key "{\"email\": {\"S\": \"$USER_ID\"}}" \
      --update-expression "SET totalWins = :zero" \
      --expression-attribute-values '{":zero": {"N": "0"}}' \
      --output json > /dev/null

    echo "Reset totalWins for userId: $USER_ID"
  done <<< "$ITEMS"

  # Check for pagination
  LAST_KEY=$(echo "$RESULT" | jq -c '.LastEvaluatedKey // empty')
  if [ -z "$LAST_KEY" ]; then
    echo "✅ Done! All records updated."
    break
  fi

  echo "Paginating to next batch..."
done
