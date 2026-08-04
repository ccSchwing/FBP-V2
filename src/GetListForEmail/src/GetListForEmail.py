from ast import List
import json
import os
from typing import Any
from urllib import request
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
logging.basicConfig(format='%(levelname)s %(message)s')
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
@app.post("/getListForEmail")   # This is the endpoint for OPTIONS
@app.post("/getListForGridSheet")
@app.post("/getListForPickSheet")
@app.post("/getListForReminders")
def getListForEmail():
    logger.info("Handling getListForEmail request")  # Log entry into the function
    try:
        logger.info(f"Raw event data: {json.dumps(app.current_event.raw_event, default=str)}")  # Log the raw event data

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({
                'error': f'exception occurred: {e}',
                'message': 'An unexpected error occurred while processing the request'
            })
        }
    # Get the request body and see what the request is for.
    body=app.current_event.json_body
    requestType=body.get('requestType')
    if requestType == "grid":
        logger.info("Processing request for grid sheet")
        fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for grid sheet", "INFO")
    if requestType == "picks":
        logger.info("Processing request for picks sheet")
        fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for picks sheet", "INFO")
    if requestType == "reminders":
        logger.info("Processing request for reminders")
        fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for reminders", "INFO")

    items= []
    match requestType:
        case "grid":
            logger.info("Processing request for grid sheet")
            fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for grid sheet", "INFO")
            # Pass the dynamoDB attribute name you want to work with.
            items= getEmailListForGrid("emailGridSheet")
        case "picks":
            logger.info("Processing request for picks sheet")
            fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for picks sheet", "INFO")
            # Pass the dynamoDB attribute name you want to work with.
            items= getEmailListForGrid("emailPickSheet")
        case "reminders":
            logger.info("Processing request for reminders")
            fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Processing request for reminders", "INFO")
            # Pass the dynamoDB attribute name you want to work with.
            items= getEmailListForGrid("emailReminders")
        case _:
            logger.error("Invalid request type")
            fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Invalid request type", "ERROR")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid request type',
                    'message': 'Please provide a valid request type (grid, picks, or reminders)'
                })
            }

    # If items is empty return it anyway    
    if items:
        return {
            'statusCode': 200,
            'body': json.dumps({
                'items': items
                })
            }

        

def getEmailListForGrid(attributeName):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(USERS_TABLE_NAME)
    items = []
    try:
        response = table.scan(
           ProjectionExpression="email, displayName, emailGridSheet, firstName",
           FilterExpression=boto3.dynamodb.conditions.Attr(attributeName).eq(True)
        )
        for item in response.get('Items', []):
            items.append({
                'email': item.get('email'),
                'displayName': item.get('displayName'),
                'firstName': item.get('firstName')
            })
        logger.info(f"Fetched gridSheet Email List from DynamoDB: {json.dumps(items, default=str) if items else 'None'}")
        return items
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "getEmailListForGrid", f"DynamoDB Error: {e}", "ERROR")
        return None
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "getEmailListForGrid", f"Unexpected error: {e}", "ERROR")
        logger.error(f"Unexpected error: {e}")
        return None

def lambda_handler(event, context):
    return app.resolve(event, context)