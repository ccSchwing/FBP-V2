from ast import List
import json
import os
from typing import Any
import boto3
import logging
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog


'''
This function will return all email addresses and displayname for the users in the FBP-Users DynamoDB table.
That data will be used by admin to view/modify profiles for users in the system.
This is GET with no parameters, it will return all users in the system with their email and display name.
'''

logger = logging.getLogger("GetFBPUser")
logger.info("Initializing GetFBPUser Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
logger.info(f"Using DynamoDB table: {USERS_TABLE_NAME}")  # Log the table name being used
fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Lambda function initialized", "INFO")

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

#  THe function below is the main logic for the lambda function.
#  It will parse the email address from the event and then call
#  the getFBPUserData function to get the user information from DynamoDB.
#  Finally, it will return the user information in the response.
@app.get("/getFBPUserEmailAndDisplayName")
@app.get("/getAllFBPUserEmailAndDisplayName")
def getAllFBPUserEmailAndDisplayName():
    logger.info("Handling getAllFBPUserEmailAndDisplayName request")  # Log entry into the function
    try:
        items= getFBPUserEmailandDisplayName()
        if items:
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'items': items
                        })
                    }
        else:
            logger.info(f"No Users found")
            return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'error': f'No users found',
                    })
            } 
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'exception occurred: {e}',
                'message': 'An unexpected error occurred while processing the request'
            })
        } 
        

def getFBPUserEmailandDisplayName():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(USERS_TABLE_NAME)
    items = []
    try:
        response = table.scan(
           ProjectionExpression="email, displayName"
        )
        for item in response.get('Items', []):
            items.append({
                'email': item.get('email'),
                'displayName': item.get('displayName')
            })
        logger.info(f"Fetched users from DynamoDB: {json.dumps(items, default=str) if items else 'None'}")
        return items
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", f"DynamoDB Error: {e}", "ERROR")
        return None
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", f"Unexpected error: {e}", "ERROR")
        logger.error(f"Unexpected error: {e}")
        return None

def lambda_handler(event, context):
    return app.resolve(event, context)