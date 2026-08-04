import boto3
import json
import os
import logging
from botocore.exceptions import ClientError
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger()
logger.info("Initializing OpenPool Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)
logger.info("OpenPool Lambda function initialized successfully")


# This lamdda function is responsible for all of the work needed to figure out who
# won for the week.
# Step 0:  Make sure the pool is closed for the week that just ended.
# If it is still open, log an error and bail.  We don't want to calculate results while the pool is still open.
# (This should have already been done by the SetPoolStatusClose Lambda, but we can be extra sure here.)
# Calculate the weekly NFL results
#
# Update the weekly results in the database, including wins/losses for each user and determining the weekly winner.
# Send out the weekly results email to all users.
# Open the pool for the next week.
# That should do it.  : -)
def openPool(event, context):
    # Make user that the pool is closed.
    # If not, bail and log an error.
    FBPConfigTableName = os.environ.get("FBPConfigTableName", "FBP-Config")
    configTable = boto3.resource("dynamodb").Table(FBPConfigTableName)
    current_week = getCurrentWeek()
    try:
        response = configTable.get_item(Key={"Week": current_week})
        if "Item" in response:
            pool_open = response["Item"].get("poolOpen", True)
            if pool_open:
                logging.error(
                    f"Pool is still open for week {current_week}. Cannot proceed with opening the pool for the new week."
                )
                fbpLog(
                    "fbpadmin@my-fbp.com",
                    "OpenPool",
                    f"Pool is still open for week {current_week}. Cannot proceed with opening the pool for the new week.",
                    "ERROR",
                )
                return {
                    "statusCode": 400,
                    "body": json.dumps(
                        {
                            "status": "error",
                            "message": f"Pool is still open for week {current_week}. Cannot proceed with opening the pool for the new week.",
                        }
                    ),
                }
            else:
                logging.info(
                    f"Pool is closed for week {current_week}. Proceeding with opening the pool for the new week."
                )
                fbpLog(
                    "fbpadmin@my-fbp.com",
                    "OpenPool",
                    f"Pool is closed for week {current_week}. Proceeding with opening the pool for the new week.",
                    "INFO",
                )
        else:
            logging.error(f"Configuration for current week {current_week} not found.")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "OpenPool",
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
            "OpenPool",
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

    ##
    # Green light.  Let's do this thing.  : -)
    # The calcWeeklyResults calculates the NFL Game Results and sets the winner for each game.
    ##

    ##
    # You need to import the results for the week that just ended before you can calculate the weekly results, so call the ImportResults Lambda first.
    # This will import the spreads and final scores for the week that just ended, which are needed to calculate the weekly results.
    ##
    ##
    # Call the ImportSpreadsAndFinalScores Lambda to import the spreads and final scores for the new week.
    # This will allow the spreads and final scores to be in place by the time the users
    # start making their picks for the new week.
    ##
    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /importSpreadsAndFinalScores",
        "rawPath": "/importSpreadsAndFinalScores",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": "",
        "requestContext": {
            "routeKey": "GET /importSpreadsAndFinalScores",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "GET",
                "path": "/importSpreadsAndFinalScores",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    lambda_client = boto3.client("lambda")

    importSpreadsAndFinalScoresFunction = os.environ.get(
        "ImportSpreadsAndFinalScores", "ImportSpreadsAndFinalScores"
    )
    response = lambda_client.invoke(
        FunctionName=importSpreadsAndFinalScoresFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(powertools_event),
    )
    if response.get("StatusCode") == 200:
        logging.info(
            f"ImportSpreadsAndFinalScores succeeded, pool is now open for the new week: {response.get('Week')}."
        )
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"ImportSpreadsAndFinalScores succeeded, pool is now open for the new week: {response.get('Week')}.",
            "INFO",
        )
    else:
        logging.error(
            f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}"
        )
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}.",
            "ERROR",
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}",
                    "details": (
                        response.get("Payload").read().decode("utf-8")
                        if response.get("Payload")
                        else {}
                    ),
                }
            ),
        }

    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /calcWeeklyResults",
        "rawPath": "/calcWeeklyResults",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "data": event.get("data", {}),
                "parent_request_id": context.aws_request_id,
                "timestamp": event.get("timestamp"),
            }
        ),
        "requestContext": {
            "routeKey": "GET /calcWeeklyResults",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "GET",
                "path": "/calcWeeklyResults",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    calcWeeklyResultsFunction = os.environ.get("CalcWeeklyResults", "CalcWeeklyResults")

    try:
        response = lambda_client.invoke(
            FunctionName=calcWeeklyResultsFunction,
            InvocationType="RequestResponse",
            Payload=json.dumps(powertools_event),
        )
        logging.info(f"Calc Weekly Results Response: {response}")
        result = json.loads(response["Payload"].read())
        logging.info(f"Calc Weekly Results Result: {result}")
        if result.get("statusCode") == 200:
            body = result.get("body")
            logging.info(f"Calc Weekly Results Body: {body}")
            if isinstance(body, str):
                body = json.loads(body)
            if result.get("statusCode") == 200:
                logging.info(f"Calc Weekly Results Body: {body}")
                logging.info("Calc Weekly Results succeeded, proceeding to next steps.")
        else:
            logging.error(
                f"Calc Weekly Results failed with status code: {result.get('statusCode')}"
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"Calc Weekly Results failed with status code: {result.get('statusCode')}",
                        "details": result.get("body", {}),
                    }
                ),
            }
    except ClientError as e:
        logging.exception(f"Error invoking Calc Weekly Results Lambda: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Error invoking Calc Weekly Results Lambda: {e}",
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

    # Next, UpdateWeeklyResults -- this one will update the user's wins/losses and determine the
    # weekly winner.

    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /updateWeeklyResults",
        "rawPath": "/updateWeeklyResults",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "data": event.get("data", {}),
                "parent_request_id": context.aws_request_id,
                "timestamp": event.get("timestamp"),
            }
        ),
        "requestContext": {
            "routeKey": "GET /updateWeeklyResults",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "GET",
                "path": "/updateWeeklyResults",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    updateWeeklyResultsFunction = os.environ.get(
        "UpdateWeeklyResults", "UpdateWeeklyResults"
    )
    logging.info(
        f"Invoking UpdateWeeklyResults Lambda function: {updateWeeklyResultsFunction}"
    )
    fbpLog(
        "fbpadmin@my-fbp.com",
        "OpenPool",
        f"Invoking UpdateWeeklyResults Lambda function: {updateWeeklyResultsFunction}",
        "INFO",
    )

    try:
        response = lambda_client.invoke(
            FunctionName=updateWeeklyResultsFunction,
            InvocationType="RequestResponse",
            Payload=json.dumps(powertools_event),
        )
        logging.info(f"UpdateWeeklyResults Response: {response}")
        result = json.loads(response["Payload"].read())
        logging.info(f"UpdateWeeklyResults Result: {result}")
        if result.get("statusCode") == 200:
            body = result.get("body")
            logging.info(f"UpdateWeeklyResults Body: {body}")
            if isinstance(body, str):
                body = json.loads(body)
                logging.info(f"UpdateWeeklyResults Body: {body}")
                logging.info("UpdateWeeklyResults succeeded, proceeding to next steps.")
                # Here you would add the logic to invoke the next Lambda functions for emailing users, updating pool status, etc.
        else:
            logging.error(
                f"UpdateWeeklyResults failed with status code: {result.get('statusCode')}"
            )
            fbpLog(
                "fbpadmin@my-fbp.com",
                "OpenPool",
                f"UpdateWeeklyResults failed with status code: {result.get('statusCode')}",
                "ERROR",
            )
            return {
                "statusCode": 500,
                "body": json.dumps(
                    {
                        "status": "error",
                        "message": f"UpdateWeeklyResults failed with status code: {result.get('statusCode')}",
                        "details": result.get("body", {}),
                    }
                ),
            }
    except ClientError as e:
        logging.exception(f"Error invoking UpdateWeeklyResults Lambda: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"Error invoking UpdateWeeklyResults Lambda: {e}",
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

    ## Call AdvancedMessagingService Lambda to send out the picksheet notification to
    # subscribed users.
    def create_message_event(messaging_data):

        return {
            "version": "2.0",
            "routeKey": "POST /advanced-messaging",
            "rawPath": "/advanced-messaging",
            "rawQueryString": "",
            "headers": {"content-type": "application/json"},
            "body": json.dumps(messaging_data),
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

    sendMessageFunction = os.environ.get(
        "AdvancedMessagingService", "AdvancedMessagingService"
    )

    ##
    # First, send the picksheet notification to all subscribed users via SMS.
    ##
    message_data = {"channel": "sms", "message_type": "picksheet"}
    sendMessageEvent = create_message_event(message_data)

    response = lambda_client.invoke(
        FunctionName=sendMessageFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(sendMessageEvent),
    )
    result = json.loads(response["Payload"].read())
    if not result.get("success"):
        logging.error(f"SendMessage failed: {result.get('error')}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"SendMessage failed: {result.get('error')}",
            "ERROR",
        )

    logging.info(f"SendMessage Response: {response}")
    fbpLog(
        "fbpadmin@my-fbp.com", "openPool", f"SendMessage Response: {response}", "INFO"
    )
    ##
    # Next, send the picksheet notification to all subscribed users via Email.
    ##
    message_data = {"channel": "email", "message_type": "picksheet"}
    sendMessageEvent = create_message_event(message_data)
    response = lambda_client.invoke(
        FunctionName=sendMessageFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(sendMessageEvent),
    )
    logging.info(f"SendMessage Response: {response}")
    fbpLog(
        "fbpadmin@my-fbp.com", "openPool", f"SendMessage Response: {response}", "INFO"
    )

    ##
    # Send out weekly winner announcement to all SMS subscribers.
    ##
    message_data = {"channel": "sms", "message_type": "weeklywinner"}
    sendMessageEvent = create_message_event(message_data)
    response = lambda_client.invoke(
        FunctionName=sendMessageFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(sendMessageEvent),
    )
    result = json.loads(response["Payload"].read())
    if not result.get("success"):
        logging.error(f"SendMessage failed: {result.get('error')}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"SendMessage failed: {result.get('error')}",
            "ERROR",
        )

    logging.info(f"SendMessage Response: {response}")
    fbpLog(
        "fbpadmin@my-fbp.com", "openPool", f"SendMessage Response: {response}", "INFO"
    )
    ##
    # Send out weekly winner announcement to all Email subscribers.
    ##
    message_data = {"channel": "email", "message_type": "weeklywinner"}
    sendMessageEvent = create_message_event(message_data)
    response = lambda_client.invoke(
        FunctionName=sendMessageFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(sendMessageEvent),
    )
    result = json.loads(response["Payload"].read())
    if not result.get("success"):
        logging.error(f"SendMessage failed: {result.get('error')}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"SendMessage failed: {result.get('error')}",
            "ERROR",
        )

    logging.info(f"SendMessage Response: {response}")
    fbpLog(
        "fbpadmin@my-fbp.com", "openPool", f"SendMessage Response: {response}", "INFO"
    )
    ##
    # Call the ImportSpreadsAndFinalScores Lambda to import the spreads and final scores for the new week.
    # This will allow the spreads and final scores to be in place by the time the users
    # start making their picks for the new week.
    ##

    setPoolOpenFunction = os.environ.get("SetPoolStatusOpen", "SetPoolStatusOpen")
    powertools_event = {
        "version": "2.0",
        "routeKey": "POST /setPoolStatusOpen",
        "rawPath": "/setPoolStatusOpen",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": '{"poolOpen": true, "create_next_week": true}',
        "requestContext": {
            "routeKey": "POST /setPoolStatusOpen",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "POST",
                "path": "/setPoolStatusOpen",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }
    response = lambda_client.invoke(
        FunctionName=setPoolOpenFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(powertools_event),
    )
    if response.get("StatusCode") == 200:
        logging.info(
            f"SetPoolStatusOpen succeeded, pool is now open for the new week: {response.get('Week')}."
        )
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"SetPoolStatusOpen succeeded, pool is now open for the new week: {response.get('Week')}.",
            "INFO",
        )
    else:
        logging.error(
            f"SetPoolStatusOpen failed with status code: {response.get('StatusCode')}"
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"SetPoolStatusOpen failed with status code: {response.get('StatusCode')}",
                    "details": (
                        response.get("Payload").read().decode("utf-8")
                        if response.get("Payload")
                        else {}
                    ),
                }
            ),
        }
        ##
    ##
    # Call the ImportSpreadsAndFinalScores Lambda to import the spreads for the new week.
    # This will allow the spreads to be in place by the time the users
    # start making their picks for the new week.
    ##
    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /importSpreadsAndFinalScores",
        "rawPath": "/importSpreadsAndFinalScores",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": "",
        "requestContext": {
            "routeKey": "GET /importSpreadsAndFinalScores",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "GET",
                "path": "/importSpreadsAndFinalScores",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }

    ##
    # Now, import the Spreads for the new week.
    # This will allow the spreads to be in place by the time the users start making their picks for the new week.
    ##
    importSpreadsAndFinalScoresFunction = os.environ.get(
        "ImportSpreadsAndFinalScores", "ImportSpreadsAndFinalScores"
    )
    response = lambda_client.invoke(
        FunctionName=importSpreadsAndFinalScoresFunction,
        InvocationType="RequestResponse",
        Payload=json.dumps(powertools_event),
    )
    if response.get("StatusCode") == 200:
        logging.info(
            f"ImportSpreadsAndFinalScores succeeded, pool is now open for the new week: {response.get('Week')}."
        )
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"ImportSpreadsAndFinalScores succeeded, pool is now open for the new week: {response.get('Week')}.",
            "INFO",
        )
    else:
        logging.error(
            f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}"
        )
        fbpLog(
            "fbpadmin@my-fbp.com",
            "openPool",
            f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}.",
            "ERROR",
        )
        return {
            "statusCode": 500,
            "body": json.dumps(
                {
                    "status": "error",
                    "message": f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}",
                    "details": (
                        response.get("Payload").read().decode("utf-8")
                        if response.get("Payload")
                        else {}
                    ),
                }
            ),
        }

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "status": "success",
                "message": "Pool opened successfully",
                "details": {"poolOpen": True, "week": getCurrentWeek()},
            }
        ),
    }
