import json
import os
import boto3
import logging
from decimal import Decimal
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib import getCurrentWeek
from fbplib import fbpLog


logger = logging.getLogger()
logger.setLevel(logging.INFO)

FBP_PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', 'FBP-Picks')
logger.info(f"Using FBP Picks DynamoDB table: {FBP_PICKS_TABLE_NAME}")
FBP_USERS_TABLE= os.environ.get('FBPUsersTableName', 'FBP-Users')
logger.info(f"Using FBP Users DynamoDB table: {FBP_USERS_TABLE}")

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)
app = APIGatewayHttpResolver(cors=cors_config)


def decimal_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


@app.get("/getAllFBPPicks")
def getAllFBPPicks():

    week = getCurrentWeek.getCurrentWeek()
    if week is None:
        fbpLog.fbpLog("fbpadmin@my-fbp.com", "GetAllFBPPicks", "Could not determine current week", "ERROR", week)
        logger.error("Could not determine current week")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Could not determine current week'}),
        }

    logger.info(f"Fetching all FBP picks for week: {week}")
    picks = getAllPicksForWeek(week)
    logger.info(f"Retrieved {len(picks)} picks for week {week}")
    fbpLog.fbpLog("fbpadmin@my-fbp.com", "GetAllFBPPicks", f"Retrieved {len(picks)} picks for week {week}", "INFO", week)
    return {
        'statusCode': 200,
        'body': json.dumps(picks, default=decimal_default),
    }


def getAllPicksForWeek(week):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_PICKS_TABLE_NAME)
    try:
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('week').eq(week)
        )
        items = response.get('Items', [])
        # Handle pagination
        while 'LastEvaluatedKey' in response:
            response = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('week').eq(week),
                ExclusiveStartKey=response['LastEvaluatedKey']
            )
            items.extend(response.get('Items', []))

        ##
        # Get the userType from FBP_USERS_TABLE for each userId and add it to the items
        # and if the type is 'user' add it to the picks list.
        # if not 'user' skip it.
        user_table = dynamodb.Table(FBP_USERS_TABLE)
        userPicks = []
        for item in items:
            email = item.get('email')
            if email:
                user_response = user_table.get_item(Key={'email': email})
                if 'Item' in user_response and user_response['Item'].get('userType') == 'user':
                    userPicks.append(item)

        userPicks.sort(key=lambda x: (x.get('displayName') or '').lower())
        return userPicks
    except ClientError as e:
        fbpLog.fbpLog("fbpadmin@my-fbp.com", "GetAllFBPPicks", f"DynamoDB Error: {e}", "ERROR", week)
        logger.error(f"DynamoDB Error: {e}")
        return []
    except Exception as e:
        fbpLog.fbpLog("fbpadmin@my-fbp.com", "GetAllFBPPicks", f"Unexpected error: {e}", "ERROR", week)
        logger.error(f"Unexpected error: {e}")
        return []


def lambda_handler(event, context):
    return app.resolve(event, context)