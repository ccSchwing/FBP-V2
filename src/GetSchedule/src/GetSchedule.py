import json
import os
import boto3
import logging
from decimal import Decimal
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.getCurrentWeek import getCurrentWeek
from fbplib.fbpLog import fbpLog

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

FBP_SCHEDULE_TABLE_NAME = os.environ.get('FBPScheduleTableName')
logger.info(f"Using FBP Schedule DynamoDB table: {FBP_SCHEDULE_TABLE_NAME}")

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)
app = APIGatewayHttpResolver(cors=cors_config)

@app.get("/getschedule")
def get_schedule():
    table = boto3.resource("dynamodb").Table(FBP_SCHEDULE_TABLE_NAME)

    # In Powertools resolver routes, this is parsed JSON when valid.
    body = app.current_event.json_body or {}

    week = getCurrentWeek()
    if week is None:
        fbpLog("fbpadmin@my-fbp-com", "GetSchedule", "Could not determine current week", "ERROR")
        return Response(
            status_code=500,
            content_type="application/json",
            body=json.dumps({'error': 'Could not determine current week'}),
        )
    try:
        response = table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('Week').eq(week)
        )
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(response.get('Items', []), default=str),
        )
    except ClientError as e:
        fbpLog("fbpadmin@my-fbp-com", "GetSchedule", f"Error querying schedule: {e}", "ERROR")
        return Response(
            status_code=500,
            content_type="application/json",
            body=json.dumps({'error': 'Error querying schedule'}),
        )


def lambda_handler(event, context):
    return app.resolve(event, context)