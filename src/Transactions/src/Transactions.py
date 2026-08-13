import os
import boto3
import hashlib
import json
import uuid
import logging
from datetime import datetime, timezone
from fbplib.fbpLog import fbpLog
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)


app = APIGatewayHttpResolver(cors=cors_config)

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table(os.getenv('TransactionsTableName'))
if not os.getenv('TransactionsTableName'):
    raise ValueError("Environment variable 'TransactionsTableName' is not set")

def compute_hash(data: dict) -> str:
    """Compute SHA-256 hash of a transaction record."""
    record_str = json.dumps(data, sort_keys=True)
    return "sha256:" + hashlib.sha256(record_str.encode()).hexdigest()

def write_transaction(tx_type, user_id, amount, previous_hash):
    transaction_id = f"txn_{uuid.uuid4().hex[:12]}"
    timestamp = datetime.now(timezone.utc).isoformat()

    # Build the record (without the hash first)
    record = {
        "transactionId": transaction_id,
        "timestamp": timestamp,
        "type": tx_type,           # "ENTRY_FEE" or "WINNER_PAYOUT"
        "userId": user_id,
        "amount": str(amount),     # DynamoDB stores decimals as strings
        "currency": "USD",
        "status": "COMPLETED",
        "previousHash": previous_hash,
    }

    # Now hash the record itself and add it
    record["recordHash"] = compute_hash(record)

    # Write to DynamoDB
    table.put_item(Item=record)
    print(f"Written: {transaction_id} | Hash: {record['recordHash']}")
    return record["recordHash"]  # Return for chaining

# Example usage:
genesis_hash = "sha256:0000000000000000"  # Starting hash for your first record

# User joins
h1 = write_transaction("ENTRY_FEE", "user_001", 10.00, genesis_hash)
h2 = write_transaction("ENTRY_FEE", "user_002", 10.00, h1)
h3 = write_transaction("ENTRY_FEE", "user_003", 10.00, h2)

# Weekly winner payout
h4 = write_transaction("WINNER_PAYOUT", "user_002", 25.00, h3)
