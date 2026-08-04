import json
from math import log
from decimal import Decimal
import os
from typing import Any, Dict, cast
import boto3
import logging
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.decimalDefault import decimal_default
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
from datetime import datetime, timezone


logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing FBPPayoutLedger Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

# Initialize the APIGatewayHttpResolver with CORS configuration
cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
    )
app = APIGatewayHttpResolver(cors=cors_config)

# Define the DynamoDB table name and initialize the DynamoDB resource
FBP_PAYOUT_LEDGER = os.environ.get('FBPPayoutLedgerTableName', 'FBP-Payout-Ledger')
dynamodb = boto3.resource('dynamodb')
ledgerTable = dynamodb.Table(FBP_PAYOUT_LEDGER)

FBP_USER_TABLE = os.environ.get('FBPUserTableName', 'FBP-Users')
userTable = dynamodb.Table(FBP_USER_TABLE)


@app.post("/deposit")
def deposit():
    try:
        body = app.current_event.json_body
        deposit_amount = body.get('depositAmount')
        if deposit_amount is None:
            logger.warning("Deposit amount not provided in the request body")  # Log missing deposit amount
            return Response(
                body=json.dumps({"error": "Deposit amount is required"}),
                status_code=400,
                headers={"Content-Type": "application/json"}
            )
        email=body.get('email')
        if email is None:
            logger.warning("Email not provided in the request body")  # Log missing email
            return Response(
                body=json.dumps({"error": "Email is required"}),
                status_code=400,
                headers={"Content-Type": "application/json"}
            )

        current_week = getCurrentWeek()
        logger.info("Processing deposit of %s for week: %s", deposit_amount, current_week)  # Log the deposit amount and week
        response=ledgerTable.query(
            KeyConditionExpression='RecordType = :recordType',
            ExpressionAttributeValues={':recordType': 'BALANCE'},
            ScanIndexForward=False,
            Limit=1
        )
        if response is not None and 'Items' in response and len(response['Items']) > 0:
            current_balance = Decimal(response['Items'][0]['currentBalance'])
        else:
            current_balance = Decimal(0)
        new_balance = current_balance + Decimal(deposit_amount)
        newRecord = {
            'week': current_week,
            'RecordType': 'BALANCE',
            'currentBalance': new_balance,
            'Timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'amount': Decimal(deposit_amount),
            'description': f'Deposit of {deposit_amount} for week {current_week}',
            'displayName': "FBP Admin",
            'email': email
        }
        ledgerTable.put_item(Item=newRecord)

        logger.info("Successfully added  deposits for week: %s", current_week)  # Log successful update
        body = {
            "message": "Deposit successful",
            "previousBalance": str(current_balance),  # Convert Decimal to string for JSON serialization
            "depositAmount": str(deposit_amount),  # Convert Decimal to string for JSON serialization"
            "newBalance": str(new_balance)  # Convert Decimal to string for JSON serialization
        }
        return Response(
            body=json.dumps(body),
            status_code=200,
            headers={"Content-Type": "application/json"}
        )
    except ClientError as e:
        error_message = e.response.get('Error', {}).get('Message', 'Unknown error')
        logger.error("DynamoDB ClientError: %s", error_message)  # Log DynamoDB errors
        return Response(
            body=json.dumps({"error": "Failed to process deposit"}),
            status_code=500,
            headers={"Content-Type": "application/json"}
        )
@app.post("/payout")
def payout():
    try:
        body = app.current_event.json_body
        payout_amount = body.get('payoutAmount')
        if payout_amount is None:
            logger.warning("Payout amount not provided in the request body")  # Log missing payout amount
            return Response(
                body=json.dumps({"error": "Payout amount is required"}),
                status_code=400,
                headers={"Content-Type": "application/json"}
            )
        email=body.get('email')
        if email is None:
            logger.warning("Email not provided in the request body")  # Log missing email
            return Response(
                body=json.dumps({"error": "Email is required"}),
                status_code=400,
                headers={"Content-Type": "application/json"}
            )

        current_week = getCurrentWeek()
        logger.info("Processing payout of %s for week: %s", payout_amount, current_week)  # Log the payout amount and week
        response=ledgerTable.query(
            KeyConditionExpression='RecordType = :recordType',
            ExpressionAttributeValues={':recordType': 'BALANCE'},
            ScanIndexForward=False,
            Limit=1
        )
        if response is not None and 'Items' in response and len(response['Items']) > 0:
            current_balance = Decimal(response['Items'][0]['currentBalance'])
        else:
            current_balance = Decimal(0)
        
        displayName=userTable.get_item(Key={'email': email}).get('Item', {}).get('displayName', 'Unknown User')

        new_balance = current_balance - Decimal(payout_amount)
        newRecord = {
            'week': current_week,
            'RecordType': 'BALANCE',
            'currentBalance': new_balance,
            'Timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'amount': Decimal(payout_amount) * -1,  # Record the payout as a negative amount in the BALANCE record
            'description': f'Payout of {payout_amount} for week {current_week}',
            'displayName': displayName,
            'email': email

        }
        ledgerTable.put_item(Item=newRecord)

        ##
        # put in a PAYOUT record.
        ##
        payoutRecord = {
            'week': current_week,
            'RecordType': 'PAYOUT',
            'currentBalance': new_balance,
            'Timestamp': datetime.now(timezone.utc).isoformat() + 'Z',
            'amount': Decimal(payout_amount),
            'description': f'Payout of {payout_amount} for week {current_week}',
            'displayName': displayName,
            'email': email

        }
        ledgerTable.put_item(Item=payoutRecord)

        logger.info("Successfully added  payout for week: %s", current_week)  # Log successful update

        ##
        # Now that the payout has been processed, the the paidUser boolean in the FBP-Users
        # table to True for the user that was paid out.
        ##
        userTable.update_item(
            Key={'email': email},
            UpdateExpression='SET isPaidUser = :isPaidUser',
            ExpressionAttributeValues={':isPaidUser': True}
        )
        logger.info("Successfully updated paidUser status for email: %s", email)  # Log successful user update
        fbpLog(email, "Payout", f"Payout of {payout_amount} processed for {displayName}",
               "INFO")
        body = {
            "message": "Payout successful",
            "previousBalance": str(current_balance),  # Convert Decimal to string for JSON serialization
            "payoutAmount": str(payout_amount),  # Convert Decimal to string for JSON serialization"
            "newBalance": str(new_balance)  # Convert Decimal to string for JSON serialization
        }
        return Response(
            body=json.dumps(body),
            status_code=200,
            headers={"Content-Type": "application/json"}
        )
    except ClientError as e:
        error_message = e.response.get('Error', {}).get('Message', 'Unknown error')
        logger.error("DynamoDB ClientError: %s", error_message)  # Log DynamoDB errors
        return Response(
            body=json.dumps({"error": "Failed to process payout"}),
            status_code=500,
            headers={"Content-Type": "application/json"}
        )
@app.get("/getFBPLedger")
def getFBPLedger():
    try:
        ##
        # Just return the most recent BALANCE record.  Has the Current Balance.
        balanceResponse = ledgerTable.query(
            KeyConditionExpression=Key('RecordType').eq('BALANCE'),
            ScanIndexForward=False,
            Limit=1
        )
        currentBalanceItems = balanceResponse.get('Items', [])
        logger.info("Successfully retrieved ledger with %d records", len(currentBalanceItems))  # Log the number of records retrieved

        ##
        # Return all PAYOUT records.
        ##
        payoutResponse = ledgerTable.query(
            KeyConditionExpression=Key('RecordType').eq('PAYOUT'),
            ScanIndexForward=False,
        )
        payoutItems = payoutResponse.get('Items', [])
        logger.info("Successfully retrieved payout records with %d records", len(payoutItems))  # Log the number of payout records retrieved

        ledgerItems = currentBalanceItems + payoutItems 
        logger.info("Returning ledger with %d total records", len(ledgerItems))  # Log the total number of records returned
        logger.info("Ledger items: %s", json.dumps(ledgerItems, default=decimal_default))  # Log the ledger items before returning
        return Response(
            body=json.dumps(ledgerItems, default=decimal_default),
            status_code=200,
            headers={"Content-Type": "application/json"}
        )
    except ClientError as e:
        error_message = e.response.get('Error', {}).get('Message', 'Unknown error')
        logger.error("DynamoDB ClientError: %s", error_message)  # Log DynamoDB errors
        return Response(
            body=json.dumps({"error": "Failed to retrieve ledger"}),
            status_code=500,
            headers={"Content-Type": "application/json"}
        )
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    logger.info("Received event: %s", json.dumps(event))  # Log the incoming event
    return app.resolve(event, context)