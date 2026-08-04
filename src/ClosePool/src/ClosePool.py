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
                # Here you would add the logic to invoke the next Lambda functions for emailing users, updating pool status, etc.
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

    # ##
    # # Send PickSheet and GridSheet to users who have opted in.
    # ##
    # powertools_event = {
    #     "version": "2.0",
    #     "routeKey": "POST /sendEmail",
    #     "rawPath": "/sendEmail",
    #     "rawQueryString": "",
    #     "headers": {"content-type": "application/json"},
    #     "body": '{"templateName": "PickSheetTemplate"}',
    #     "requestContext": {
    #         "http": {
    #             "method": "POST",
    #             "path": "/sendEmail",
    #             "protocol": "HTTP/1.1",
    #             "sourceIp": "127.0.0.1",
    #             "userAgent": "sam-local",
    #         },
    #         "routeKey": "POST /sendEmail",
    #         "stage": "$default",
    #     },
    #     "isBase64Encoded": False,
    # }

    # sendEmailFunction = os.environ.get("SendEmail", "SendEmail")
    # response = lambda_client.invoke(
    #     FunctionName=sendEmailFunction,
    #     InvocationType="RequestResponse",
    #     Payload=json.dumps(powertools_event),
    # )
    # logging.info(f"SendEmail Response: {response}")
    # result = json.loads(response["Payload"].read())
    # logging.info(f"SendEmail Result: {result}")
    # if result.get("statusCode") == 200:
    #     body = result.get("body")
    #     logging.info(f"SendEmail Body: {body}")
    #     if isinstance(body, str):
    #         body = json.loads(body)
    #     if result.get("statusCode") == 200:
    #         logging.info(f"SendEmail Body: {body}")
    #         logging.info("SendEmail succeeded, proceeding to next steps.")
    #         # Here you would add the logic to invoke the next Lambda functions for emailing users, updating pool status, etc.
    # else:
    #     logging.error(f"SendEmail failed with status code: {result.get('statusCode')}")
    #     return {
    #         "statusCode": 500,
    #         "body": json.dumps(
    #             {
    #                 "status": "error",
    #                 "message": f"SendEmail failed with status code: {result.get('statusCode')}",
    #                 "details": result.get("body", {}),
    #             }
    #         ),
    #     }
    ##
    # Send GridSheet to users who have opted in.
    ##
    powertools_event = {
        "version": "2.0",
        "routeKey": "POST /sendEmail",
        "rawPath": "/sendEmail",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": '{"templateName": "GridSheetTemplate"}',
        "requestContext": {
            "http": {
                "method": "POST",
                "path": "/sendEmail",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
            "routeKey": "POST /sendEmail",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }

    sendEmailFunction = os.environ.get("SendEmail", "SendEmail")
    response = lambda_client.invoke(
        FunctionName=sendEmailFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(powertools_event),
    )
    logging.info(f"SendEmail Response: {response}")
    result = json.loads(response["Payload"].read())
    logging.info(f"SendEmail Result: {result}")
    if result.get("statusCode") == 200:
        body = result.get("body")
        logging.info(f"SendEmail Body: {body}")
        if isinstance(body, str):
            body = json.loads(body)
        if result.get("statusCode") == 200:
            logging.info(f"SendEmail Body: {body}")
            logging.info("SendEmail succeeded, proceeding to next steps.")
            # Here you would add the logic to invoke the next Lambda functions for emailing users, updating pool status, etc.
    else:
        logging.error(f"SendEmail failed with status code: {result.get('statusCode')}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"SendEmail failed with status code: {result.get('statusCode')}",
                    "details": result.get("body", {}),
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
def lambda_handler(event, context) -> dict[str, Any]:
    logging.info(f"Received event: {event}")
    return app.resolve(event, context)
