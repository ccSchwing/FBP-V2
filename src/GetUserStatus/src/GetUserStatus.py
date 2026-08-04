import json
import os
import boto3
import logging
from typing import Dict, Any
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
from fbplib.decimalDefault import decimal_default

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger("QueryFBPLogs")
logger.info("Initializing QueryFBPLogs Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

# This lambda will check the status of two things:
# 1. If the user is a Paid User
# 2. Is the user's account locked?

USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
LOGS_TABLE_NAME = os.environ.get('FBPLogsTableName', '2025-Log')

userTable = boto3.resource('dynamodb').Table(USERS_TABLE_NAME)
logTable = boto3.resource('dynamodb').Table(LOGS_TABLE_NAME)

logger.info(f"Using DynamoDB tables - Users: {USERS_TABLE_NAME}, Logs: {LOGS_TABLE_NAME}")

cors_config = CORSConfig(
allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
max_age=86400,  # Cache preflight for 24 hours
 allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

@app.post("/getUserStatus")
def get_user_status() -> Response:
    logger.info("Handling getUserStatus request")  # Log entry into the function
    try:
        request_body = app.current_event.json_body
        logger.info(f"Request body: {request_body}")
        if not request_body:
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", "ERROR", "No JSON body found in the request")
            logger.error("No JSON body found in the request")
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Invalid request body',
                    'message': 'Request body seems to be empty or not valid JSON'
                })
            )
        email = request_body.get('email')
        if email is None:
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="ERROR", details="email is missing from the request body")  
            logger.error("email is missing from the request body")
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Missing email',
                    'message': 'email is required in the request body'
                })
            )
        
        userData = userTable.get_item(Key={'email': email})
        if 'Item' not in userData:
            logger.error(f"No user found with email: {email}")
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="ERROR", details=f"No user found with email: {email}")
            return Response(
                status_code=404,
                content_type="application/json",
                body=json.dumps({
                    'error': 'User Not Found',
                    'message': f'No user found with email: {email}'
                })
            ) 
        isPaidUser = userData['Item'].get('isPaidUser')
        if isPaidUser is False:
            logger.info(f"User {email} is not a paid user")
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="INFO", details=f"User {email} is not a paid user")
        else:
            logger.info(f"User {email} is a paid user")
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="INFO", details=f"User {email} is a paid user")
        isAccountLocked = userData['Item'].get('isAccountLocked')
        if isAccountLocked:
            logger.info(f"User {email} account is locked")
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="INFO", details=f"User {email} account is locked")
        else:
            logger.info(f"User {email} account is not locked")
            fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="INFO", details=f"User {email} account is not locked")
        # Placeholder response for demonstration purposes
        response_data = {
            'email': email,
            'isPaidUser': isPaidUser,
            'isAccountLocked': isAccountLocked
        }
        
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(response_data)
        )
        
    except Exception as e:
        logger.error(f"Error processing getUserStatus request: {str(e)}")
        fbpLog("fbpadmin@my-fbp.com", "getUserStatus", level="ERROR", details=f"Error processing getUserStatus request: {str(e)}")
        return Response(
            status_code=500,
            content_type="application/json",
            body=json.dumps({
                'error': 'Internal Server Error',
                'message': str(e)
            })
        )


def lambda_handler(event, context):
    return app.resolve(event, context)