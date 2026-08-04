import json
import os
import random
import re
import boto3
import logging
import hashlib
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logger = logging.getLogger()
logger.info("Initializing GetSMSVerificationCode Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

@app.post("/getSMSVerificationCode")
def getVerificationCode():

    ##
    # get the mobile number from the event body
    ##
    event_body = app.current_event.json_body
    email=event_body.get("email")
    if email is None:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Email is required'}),
        }
    ## Get the verification_code_hash for the given email
    ##
    try:
        dynamodb = boto3.resource('dynamodb')
        FBP_USERS_TABLE=os.environ.get('FBPUsersTableName')
        usersTable = dynamodb.Table(FBP_USERS_TABLE)
        response = usersTable.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        ##
        # if reponse is an empty array, it's an error
        ##
        if not response['Items']:
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'No verification code hash found for this email'}),
            }
        verification_code_hash = response['Items'][0]['verification_code_hash']
        if verification_code_hash is None:
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'No verification code hash found for this email'}),
            }
        return {
            'statusCode': 200,
            'body': json.dumps({'verification_code_hash': verification_code_hash}),
        }
    except Exception as e:

        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not retrieve verification code', 'error': str(e)}),
        }





def lambda_handler(event, context):
    return app.resolve(event, context)  