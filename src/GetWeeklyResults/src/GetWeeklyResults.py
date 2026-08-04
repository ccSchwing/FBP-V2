from calendar import c
import email
import json
from decimal import Decimal
from math import pi
from operator import index
import os
import re
from typing import Any, List, Dict
import boto3
import logging
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib import getCurrentWeek


'''
This function retrieves the weekly results for each user based on their picks and the actual game results for the week.
It queries the FBPWeeklyResults table for the current week and returns the results sorted by the
number of correct picks. It also updates the winner field for the user with the most correct picks.
This is used by the front end to display the weekly results sheet for each user.
'''

logger = logging.getLogger()
logger.info("Initializing GetWeeklyResults Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

@app.get("/getWeeklyResults")
def getWeeklyResults():
    FBP_WEEKLY_RESULTS_TABLE = os.environ.get('FBPWeeklyResults2025TableName', 'FBP-Weekly-Results-2025')
    logger.info(f"Using DynamoDB table: {FBP_WEEKLY_RESULTS_TABLE}")  # Log the table name being used
    fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", "Lambda function initialized", "INFO")
    fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", "Retrieving weekly results", "INFO")
   
    FBP_USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
    logger.info(f"Using FBP Users DynamoDB table: {FBP_USERS_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    resultsTable = dynamodb.Table(FBP_WEEKLY_RESULTS_TABLE) 
    usersTable = dynamodb.Table(FBP_USERS_TABLE_NAME)

    def decimal_default(value):
        if isinstance(value, Decimal):
            return int(value) if value % 1 == 0 else float(value)
        raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

    week=getCurrentWeek.getCurrentWeek()
    if week is None:
        fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", "Could not determine current week", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not determine current week'}),
        }
    # If week == 1, there are no results to show, so we can return early with 
    # a message indicating that results will be available after week 1.
    if int(week) == 1:
        fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", "Week 1: No results to show", "INFO")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Results will be available after week 1'}),
        }
    # Subtract 1 from week to get results for the previous week.
    week=week-1
    logger.info(f"Retrieving results for week: {week}")
    fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", f"Retrieving results for week: {week}", "INFO")
    try:
        # Filter the scan for the current week's results.
        response = resultsTable.scan(
            FilterExpression=Attr('week').eq(Decimal(week))
        )

        allUserPicks  = response.get('Items', [])
        if not allUserPicks:
            logger.warning(f"No picks found for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", f"No picks found for week {week}", "WARNING")
            return {
                'statusCode': 404,
                'body': json.dumps({'message': f'No picks found for week {week}'}),
            }
        # get the displaName from usersTable for each user and add it to the results.
        userPicks = []
        for user in allUserPicks:
            email = user['email']
            userResponse = usersTable.get_item(Key={'email': email})
            userItem = userResponse.get('Item')
            if userItem['userType'] == 'user':
                if userItem:
                    user['displayName'] = userItem.get('displayName', 'Unknown User')
                else:
                    user['displayName'] = 'Unknown User'
                userPicks.append(user)
            # Skip of userType is not 'user'
        sortedPicks=sortWeeklyResults(picks=userPicks)
        return {
            'statusCode': 200,
            'body': json.dumps(sortedPicks, default=decimal_default),
        }
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", f"DynamoDB Error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'DynamoDB Error'}),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "GetWeeklyResults", f"Unexpected error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Unexpected error'}),
        }


def sortWeeklyResults(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(picks, key=lambda x: x['correctpicks'], reverse=True)

def lambda_handler(event, context):
    return app.resolve(event, context)  