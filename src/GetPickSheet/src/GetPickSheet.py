import json
import logging
import os
from decimal import Decimal
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

logger.info("Init: GetPickSheet Lambda")
TABLE_NAME = os.environ.get("FBPScheduleTableName", "FBP-Schedule")

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


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")




@app.get("/getPickSheet")
def getPickSheet() -> dict[str, Any]:
    table = boto3.resource("dynamodb").Table(TABLE_NAME)

    # In Powertools resolver routes, this is parsed JSON when valid.
    body = app.current_event.json_body or {}

    week=getCurrentWeek()
    email=body.get("email")
    if email is None: 
        fbpLog("fbpadmin@my-fbp-com", "GetPickSheet", "Email address is required in the request body", "ERROR")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Email address is required in the request body"}),
        }
    if week is None:
        fbpLog("fbpadmin@my-fbp-com", "GetPickSheet", "Could not determine current week", "ERROR")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Could not determine current week"}),
        }
    try:
        # get all picks for the current week
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Week').eq(week)
        )
        schedule: list[Any] = response.get('Items', []) 
        if not schedule:
            logger.warning(f"No picks found for week {week}")
            fbpLog(email=email, action="GetPickSheet", details=f"No picks found for week {week}", level="WARNING")
            return {
                "statusCode": 404,
                "body": json.dumps({"error": f"No picks found for week {week}"}),
            }
        else:
            logger.info(f"Retrieved {len(schedule)} picks for week {week}")
            fbpLog(email=email, action="GetPickSheet", details=f"Retrieved {len(schedule)} picks for week {week}", level="INFO")
            return {
                "statusCode": 200,
                "body": schedule,
            }
    except ClientError as e:
        logger.exception("DynamoDB update failed")
        fbpLog("fbpadmin@my-fbp-com", "GetPickSheet", f"DynamoDB update failed: {str(e)}", "ERROR")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "DynamoDB update failed", "detail": str(e)}),
        }



def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return app.resolve(event, context)
