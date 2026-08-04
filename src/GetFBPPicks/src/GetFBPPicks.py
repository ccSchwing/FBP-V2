from calendar import week
import json
import os
from webbrowser import get
import boto3
import logging
from decimal import Decimal
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek




'''
This function will return the user picks for the given email address in the event.
'''

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.info("Init: GetFBPPicksPython Lambda")
FBP_PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', 'FBP-Picks')

cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=[
        "Content-Type",
        "X-Amz-Date",
        "Authorization",
        "X-Api-Key",
        "X-Amz-Security-Token",
    ],
    max_age=86400,
    allow_credentials=False,
)

app = APIGatewayHttpResolver(cors=cors_config)


def decimal_default(value):
    if isinstance(value, Decimal):
        # Preserve whole numbers as ints; keep non-whole values as floats.
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

@app.post("/getPicksForUser")
@app.post("/getFBPPicksPython")
def getPicksForUser():
    try:
        body = app.current_event.json_body
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        logger.info(f"Parsed JSON body: {body}")
        email = body.get('email')
        logger.info(f"Extracted email from API Gateway event: {email}")
    except json.JSONDecodeError:
        logger.error("Invalid JSON in request body")
        fbpLog("fbpadmin@my-fbp-com", "GetFBPPicksPython", "Invalid JSON in request body", "ERROR")
        return Response(
            status_code=400,
            content_type="application/json",
            body=json.dumps({
                'error': 'Invalid JSON',
                'message': 'Request body must be valid JSON'
            })
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp-com", "GetFBPPicksPython", f"Unexpected error: {e}", "ERROR")
        return Response(
            status_code=400,
            content_type="application/json",
            body=json.dumps({
                'error': 'Invalid request body',
                'message': 'Request body must be valid JSON with an email field'
            })
        )

    if not email:  
        logger.error("Email address is required in request body")
        fbpLog("fbpadmin@my-fbp-com", "GetFBPPicksPython", "Email address is required in request body", "ERROR")
        return Response(
            status_code=400,
            content_type="application/json",
            body=json.dumps({
                'error': 'Email address is required',
                'message': 'Please provide email address in the event'
            })
        )
    picksData = getPicks(email)

    week = getCurrentWeek()
    week=int(week) if week is not None else None
    if picksData is not None and 'week' in picksData and int(picksData['week']) != int(week):
        logger.info(f"User {email} has picks for week {picksData['week']}, but current week is {week}. Returning empty picks.")
        picksData['picks'] = []
        picksData['tieBreaker'] = 0
    
    if picksData is not None:

        # The "normal" case is where the week is the current week,
        # and the user has made not picks yet.
        # so return what you find.

        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps({
                'email': picksData.get('email'),
                'displayName': picksData.get('displayName'),
                'picks': picksData.get('picks'),
                'tieBreaker': picksData.get('tieBreaker'),
                'week': week
            }, default=decimal_default)
        )
    else:
        logger.error(f"User not found: {email}")
        fbpLog("fbpadmin@my-fbp-com", "GetFBPPicksPython", f"User not found: {email}", "ERROR")
        return Response(
            status_code=404,
            content_type="application/json",
            body=json.dumps({
                'error': f'User with email {email} not found',
                'email': email
            })
        )
        

def getPicks(emailAddress):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_PICKS_TABLE_NAME)
    try:
        # I need to see if there are any picks for the current week.
        # The week value I get is not important.
        # I'm going to get the current week after I return from this method.

        response = table.get_item(Key={'email': emailAddress})
        picksData = response['Item'] if 'Item' in response else None

        # The primary key lookup is by email; apply week check in code.
        if picksData is not None:
            # item_week = item.get('week')
            # if week is None or item_week is None or int(item_week) != int(week):
                # return None

            return picksData
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None


def lambda_handler(event, context):
    return app.resolve(event, context)