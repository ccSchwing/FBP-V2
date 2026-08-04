import json
import logging
import os
from typing import Any

import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

logger.info("Init: GetTeamRecords Lambda")

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

@app.get("/getTeamRecords")
def getTeamRecords() -> dict[str, Any]:
    logger.info("Fetching team records")
    try:
        dynamodb = boto3.resource("dynamodb")
        FBP_RECORD_TABLE_NAME = dynamodb.Table(os.environ["FBPTeamRecordsTableName"])
        table = boto3.resource("dynamodb").Table(FBP_RECORD_TABLE_NAME.name)
        response = table.scan()
        teamRecords: list[Any] = response.get("Items", [])
        ##
        # put the items into a JSON array and return it
        ## In Powertools resolver routes, this is parsed JSON when valid.
        body ={"items": teamRecords}
        return {
            "statusCode": 200,
            "body": json.dumps(body, default=str),
        }
    except ClientError as e:
        logger.error(f"Error fetching team records: {e}")
        fbpLog("fbpadmin@my-fbp-com", "GetTeamRecords", f"Error fetching team records: {e}", "ERROR")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching team records"}),
        }
        
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return app.resolve(event, context)