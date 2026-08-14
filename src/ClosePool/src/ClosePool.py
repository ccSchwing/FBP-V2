import boto3
import json
import os
import logging
import json
import os
import boto3
import logging
from typing import Any, Dict
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig, ProxyEventType
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
from aws_lambda_powertools import Tracer
tracer = Tracer()



logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger()
logger.info("Initializing ClosePool Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)
logger.info(
    "ClosePool Lambda function initialized successfully"
)  # Log successful initialization


USERS_TABLE_NAME = os.environ.get("FBPUsersTableName", "FBP-Users")
logger.info(f"Using DynamoDB table: {USERS_TABLE_NAME}")
# fbpLog("fbpadmin@my-fbp.com", "ClosePool", "Lambda function initialized", "INFO")

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
app = APIGatewayHttpResolver(proxy_type=ProxyEventType.APIGatewayProxyEventV2, cors=cors_config)
# app = APIGatewayHttpResolver(cors=cors_config)

##
# Close to Pool
##
@tracer.capture_method
@app.get("/closePool")
def closePool():
    logging.info("Handling closePool request")
    fbpLog("fbpadmin@my-fbp.com", "ClosePool", "Handling closePool request", "INFO")
    # Make user that the pool is closed.
    # If not, bail and log an error.
    FBPConfigTableName = os.environ.get("FBPConfigTableName", "FBP-Config")
    configTable = boto3.resource("dynamodb").Table(FBPConfigTableName)
    current_week = getCurrentWeek()
    try:
        response = configTable.get_item(Key={"Week": current_week})
        if "Item" in response:
            pool_open = response["Item"].get("poolOpen", False)
            if pool_open == False:
                logging.error(
                    f"Pool is already closed for week {current_week}. Cannot proceed with closing the pool for the current week."
                )
                fbpLog(
                    "fbpadmin@my-fbp.com",
                    "ClosePool",
                    f"Pool is already closed for week {current_week}. Cannot proceed with closing the pool for the current week.",
                    "ERROR",
                )
                return {
                    "statusCode": 400,
                    "body": json.dumps(
                        {
                            "status": "error",
                            "message": f"Pool is already closed for week {current_week}. Cannot proceed with closing the pool for the current week.",
                        }
                    ),
                }
            else:
                logging.info(
                    f"Pool is currently open for week {current_week}. Proceeding with closing the pool for the current week."
                )
                fbpLog(
                    "fbpadmin@my-fbp.com",
                    "ClosePool",
                    f"Pool is currently open for week {current_week}. Proceeding with closing the pool for the current week.",
                    "INFO",
                )
                configTable.update_item(
                    Key={"Week": current_week},
                    UpdateExpression="SET poolOpen = :open",
                    ExpressionAttributeValues={":open": False},
                )
        else:
            logging.error(f"Configuration for current week {current_week} not found.")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "ClosePool",
                f"Configuration for current week {current_week} not found.",
                "ERROR",
            )
            return {
                "statusCode": 404,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"Configuration for current week {current_week} not found.",
                    }
                ),
            }

    except ClientError as e:
        logging.exception(f"Error checking pool status for week {current_week}: {e}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "ClosePool",
            f"Error checking pool status for week {current_week}: {e}",
            "ERROR",
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Error checking pool status for week {current_week}: {e}",
                }
            ),
        }

    # Defind the lambda client
    lambda_client = boto3.client("lambda")

    ##
    # Validate picks.  If there are missing picks, make them using the user's default algorithm.
    ##

    powertools_event = {
        "version": "2.0",
        "routeKey": "POST /validateAndFixFBPPicks",
        "rawPath": "/validateAndFixFBPPicks",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": "{}",
        "requestContext": {
            "routeKey": "POST /validateAndFixPicks",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "POST",
                "path": "/validateAndFixPicks",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    ##
    # Call the validateAndFixFBPPicks Lambda function to validate user
    # picks and fix any missing picks using the user's default algorithm.
    # Get the Lambda function name from environment variable or use a default value
    saveFBPPicksFunction = os.environ.get("SaveFBPPicks", "SaveFBPPicks")
    logging.info(
        f"Invoking SaveFBPPicks Lambda function: {saveFBPPicksFunction} with event: {powertools_event}"
    )
    try:
        response = lambda_client.invoke(
            FunctionName=saveFBPPicksFunction,
            InvocationType="RequestResponse",
            Payload=json.dumps(powertools_event),
        )
        logging.info(f"SaveFBPPicks Response: {response}")
        result = json.loads(response["Payload"].read())
        logging.info(f"SaveFBPPicks Result: {result}")
        if result.get("statusCode") == 200:
            body = result.get("body")
            logging.info(f"SaveFBPPicks Body: {body}")
            if isinstance(body, str):
                body = json.loads(body)
            if result.get("statusCode") == 200:
                logging.info(f"SaveFBPPicks Body: {body}")
                logging.info("SaveFBPPicks succeeded, proceeding to next steps.")
        else:
            logging.error(
                f"SaveFBPPicks failed with status code: {result.get('statusCode')}"
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"SaveFBPPicks failed with status code: {result.get('statusCode')}",
                        "details": result.get("body", {}),
                    }
                ),
            }
    except ClientError as e:
        logging.exception(f"Error invoking SaveFBPPicks Lambda: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Error invoking SaveFBPPicks Lambda: {e}",
                    "details": str(e),
                }
            ),
        }
    except Exception as e:
        logging.exception(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Unexpected error: {e}",
                    "details": str(e),
                }
            ),
        }

    ##
    # Send gridsheet via AdvancedMessagingService for each channel.
    advancedMessagingServiceFunction = os.environ.get("AdvancedMessagingService", "AdvancedMessagingService")
    for channel in ["email", "sms"]:
        powertools_event = {
            "version": "2.0",
            "routeKey": "POST /advanced-messaging",
            "rawPath": "/advanced-messaging",
            "rawQueryString": "",
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"message_type": "gridsheet", "channel": channel}),
            "requestContext": {
                "http": {
                    "method": "POST",
                    "path": "/advanced-messaging",
                    "protocol": "HTTP/1.1",
                    "sourceIp": "127.0.0.1",
                    "userAgent": "sam-local",
                },
                "routeKey": "POST /advanced-messaging",
                "stage": "$default",
            },
            "isBase64Encoded": False,
        }
        response = lambda_client.invoke(
            FunctionName=advancedMessagingServiceFunction,
            InvocationType="RequestResponse",
            Payload=json.dumps(powertools_event),
        )
        result = json.loads(response["Payload"].read())
        logging.info(f"AdvancedMessagingService [{channel}] Result: {result}")
        if not result.get("success"):
            logging.error(f"AdvancedMessagingService [{channel}] failed with status code: {result.get('error')}")
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"AdvancedMessagingService [{channel}] failed with error: {result.get('error')}",
                        "details": result,
                    }
                ),
            }

    # Get the Lambda function name from environment variable or use a default value
    setPoolStatusClosed = os.environ.get("SetPoolStatusClosed", "SetPoolStatusClosed")
    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /setPoolStatusClosed",
        "rawPath": "/setPoolStatusClosed",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "requestContext": {
            "routeKey": "GET /setPoolStatusClosed",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "GET",
                "path": "/setPoolStatusClosed",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    logging.info(
        f"Invoking SetPoolStatusClosed Lambda function: {setPoolStatusClosed} with event: {powertools_event}"
    )
    try:
        response = lambda_client.invoke(
            FunctionName=setPoolStatusClosed,
            InvocationType="RequestResponse",
            Payload=json.dumps(powertools_event),
        )
        logging.info(f"SetPoolStatusClosed Response: {response}")
        result = json.loads(response["Payload"].read())
        logging.info(f"SetPoolStatusClosed Result: {result}")
        if result.get("statusCode") == 200:
            body = result.get("body")
            logging.info(f"SetPoolStatusClosed Body: {body}")
            if isinstance(body, str):
                body = json.loads(body)
            if result.get("statusCode") == 200:
                logging.info(f"SetPoolStatusClosed Body: {body}")
                logging.info("SetPoolStatusClosed succeeded, proceeding to next steps.")
                # Here you would add the logic to invoke the next Lambda functions for emailing users, updating pool status, etc.
        else:
            logging.error(
                f"SetPoolStatusClosed failed with status code: {result.get('statusCode')}"
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"SetPoolStatusClosed failed with status code: {result.get('statusCode')}",
                        "details": result.get("body", {}),
                    }
                ),
            }
    except ClientError as e:
        logging.exception(f"Error invoking SetPoolStatusClosed Lambda: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Error invoking SetPoolStatusClosed Lambda: {e}",
                    "details": str(e),
                }
            ),
        }
    except Exception as e:
        logging.exception(f"Unexpected error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Unexpected error: {e}",
                    "details": str(e),
                }
            ),
        }
@tracer.capture_lambda_handler
def lambda_handler(event, context) -> dict[str, Any]:
    logging.info(f"Received event: {event}")
    logger.info("ccs was here!")
    return app.resolve(event, context)
