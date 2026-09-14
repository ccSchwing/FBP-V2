from calendar import c
import email
import json
from decimal import Decimal
from math import pi
from operator import index
import os
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
This function will retrieve the partial results for the week based on user picks and actual game outcomes.
Users can see how they did on Monday morning after the games have been played and only the MNF game is left.
Called from HTML page.
'''

logger = logging.getLogger()
logger.info("Initializing GetPartialResults Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

@app.get("/getPartialResults")
def getPartialResults():
    FBP_WEEKLY_RESULTS_TABLE = os.environ.get('FBPWeeklyResultsTableName', '2026-FBP-Weekly-Results')
    logger.info(f"Using DynamoDB table: {FBP_WEEKLY_RESULTS_TABLE}")  # Log the table name being used
    fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", "Lambda function initialized", "INFO")
    fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", "Retrieving weekly results", "INFO")
   
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
        fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", "Could not determine current week", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not determine current week'}),
        }
    logger.info(f"Retrieving results for week: {week}")
    fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", f"Retrieving partialresults for week: {week}", "INFO")
    try:
        # Filter the scan for the current week's results.
        response = resultsTable.scan(
            FilterExpression=Attr('week').eq(Decimal(week))
        )

        allUserPicks  = response.get('Items', [])
        if not allUserPicks:
            logger.warning(f"No picks found for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", f"No picks found for week {week}", "WARNING")
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
        fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", f"DynamoDB Error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'DynamoDB Error'}),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "GetPartialResults", f"Unexpected error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Unexpected error'}),
        }


def sortWeeklyResults(picks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(picks, key=lambda x: x['correctpicks'], reverse=True)

def lambda_handler(event, context):
    return app.resolve(event, context)  