import json
import os
import boto3
import logging
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
from fbplib.decimalDefault import decimal_default

logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger("QueryFBPLogs")
logger.info("Initializing QueryFBPLogs Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)


CONFIG_TABLE_NAME = os.environ.get("FBPConfigTableName", "FBP-Config")
LOGS_TABLE_NAME = os.environ.get("FBPLogsTableName", "2025-Log")
logger.info(
    f"Using DynamoDB tables - Config: {CONFIG_TABLE_NAME}, Logs: {LOGS_TABLE_NAME}"
)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=[
        "Content-Type",
        "X-Amz-Date",
        "Authorization",
        "X-Api-Key",
        "X-Amz-Security-Token",
    ],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False,
)

app = APIGatewayHttpResolver(cors=cors_config)


@app.post("/queryFBPLogs")
def query_fbp_logs():
    logger.info("Handling queryFBPLogs request")  # Log entry into the function
    try:
        startDate = None
        endDate = None
        week = None
        logLevel = None

        request_body = app.current_event.json_body
        logger.info(f"Request body: {request_body}")
        if not request_body:
            logger.error("No JSON body found in the request")
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps(
                    {
                        "error": "Invalid request body",
                        "message": "Request body seems to be empty or not valid JSON",
                    }
                ),
            )
        week_raw = request_body.get("week")
        # Frontend may send week as an empty string; treat that as not provided.
        week = None if week_raw in (None, "") else week_raw
        if week is None:
            startDate = request_body.get("startDate")
            if not startDate:
                logger.error("startDate is missing from the request body")
                return Response(
                    status_code=400,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "error": "Missing startDate",
                            "message": "startDate is required in the request body",
                        }
                    ),
                )
            endDate = request_body.get("endDate")
            if not endDate:
                logger.error("endDate is missing from the request body")
                return Response(
                    status_code=400,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "error": "Missing endDate",
                            "message": "endDate is required in the request body",
                        }
                    ),
                )
            logger.info(
                f"Extracted startDate: {startDate}, endDate: {endDate} from API Gateway event"
            )
        else:
            try:
                week = int(week)
            except (TypeError, ValueError):
                logger.error(f"Invalid week value in request body: {week_raw}")
                return Response(
                    status_code=400,
                    content_type="application/json",
                    body=json.dumps(
                        {
                            "error": "Invalid week",
                            "message": "week must be a non-empty integer",
                        }
                    ),
                )
            logger.info(f"Extracted week: {week} from API Gateway event")
            logger.info("Using only the week and the logLevel for querying the logs")
        logLevel = request_body.get("logLevel")
        if week is not None:
            logger.info("Using only the week and the logLevel for querying the logs")
        logger.info(f"Extracted logLevel: {logLevel} from API Gateway event")
        logTable = boto3.resource("dynamodb").Table(LOGS_TABLE_NAME)

        ##
        # when you get here, you have either week and logLevel or startDate, endDate, and logLevel
        # Get all logs regardless of logLevel or filter by logLevel if provideod
        # Do we care about what week it is?  I don't think so.
        if logLevel == "ALL":
            ##
            # Query for each log level separately and combine results to ensure we get all logs regardless of log level
            # This is necessary because DynamoDB does not support OR conditions in KeyConditionExpression
            ##
            # Query for INFO logs
            if week is None:
                info_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel AND #ts BETWEEN :startDate AND :endDate",
                    ExpressionAttributeNames={"#ts": "timestamp", "#lvl": "level"},
                    ExpressionAttributeValues={
                        ":logLevel": "INFO",
                        ":startDate": startDate,
                        ":endDate": endDate,
                    },
                )
                # Query for ERROR logs
                error_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel AND #ts BETWEEN :startDate AND :endDate",
                    ExpressionAttributeNames={"#ts": "timestamp", "#lvl": "level"},
                    ExpressionAttributeValues={
                        ":logLevel": "ERROR",
                        ":startDate": startDate,
                        ":endDate": endDate,
                    },
                )
                # Query for WARNING logs
                warning_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel AND #ts BETWEEN :startDate AND :endDate",
                    ExpressionAttributeNames={"#ts": "timestamp", "#lvl": "level"},
                    ExpressionAttributeValues={
                        ":logLevel": "WARNING",
                        ":startDate": startDate,
                        ":endDate": endDate,
                    },
                )
            if week is not None:
                info_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel",
                    FilterExpression="#wk = :week",
                    ExpressionAttributeNames={"#lvl": "level", "#wk": "week"},
                    ExpressionAttributeValues={":logLevel": "INFO", ":week": week},
                )
                # Query for ERROR logs
                error_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel",
                    FilterExpression="#wk = :week",
                    ExpressionAttributeNames={"#lvl": "level", "#wk": "week"},
                    ExpressionAttributeValues={":logLevel": "ERROR", ":week": week},
                )
                # Query for WARNING logs
                warning_response = logTable.query(
                    KeyConditionExpression="#lvl = :logLevel",
                    FilterExpression="#wk = :week",
                    ExpressionAttributeNames={"#lvl": "level", "#wk": "week"},
                    ExpressionAttributeValues={":logLevel": "WARNING", ":week": week},
                )
            # Combine all log entries
            items = (
                info_response.get("Items", [])
                + error_response.get("Items", [])
                + warning_response.get("Items", [])
            )
            items.sort(key=lambda x: x["timestamp"], reverse=True)
            logger.info(f"Query returned {len(items)} log entries")
            logger.info(f"Log entries: {json.dumps(items, default=decimal_default)}")
            return Response(
                status_code=200,
                content_type="application/json",
                body=json.dumps(items, default=decimal_default),
            )
        elif week is None and logLevel != "ALL":
            response = logTable.query(
                KeyConditionExpression="#lvl = :lvl AND #ts BETWEEN :startDate AND :endDate",
                ExpressionAttributeNames={"#ts": "timestamp", "#lvl": "level"},
                ExpressionAttributeValues={
                    ":lvl": logLevel,
                    ":startDate": startDate,
                    ":endDate": endDate,
                },
            )
        else:  ## Query just for week and logLevel
            response = logTable.query(
                KeyConditionExpression="#lvl = :lvl",
                FilterExpression="#wk = :week",
                ExpressionAttributeNames={"#lvl": "level", "#wk": "week"},
                ExpressionAttributeValues={":lvl": logLevel, ":week": week},
            )
        items = response.get("Items", [])
        items.sort(key=lambda x: x["timestamp"], reverse=True)
        logger.info(f"Query returned {len(items)} log entries")
        logger.info(f"Log entries: {json.dumps(items, default=decimal_default)}")
        return Response(
            status_code=200,
            content_type="application/json",
            body=json.dumps(items, default=decimal_default),
        )
    except Exception as e:
        logger.error(f"Error parsing request body: {e}")
        return Response(
            status_code=400,
            content_type="application/json",
            body=json.dumps(
                {
                    "error": "Invalid request body",
                    "message": f"Error parsing request body: {str(e)}",
                }
            ),
        )


def lambda_handler(event, context):
    return app.resolve(event, context)
