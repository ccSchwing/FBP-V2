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
FBP_PICKS_TABLE_NAME = os.environ.get("FBPPicksTableName", "FBP-Picks")
FBP_SCHEDULE_TABLE_NAME = os.environ.get("FBPScheduleTableName", "FBP-Schedule")
S3_BUCKET_NAME = os.environ.get("S3BucketName", "my-fbp.com")
CLOUDFRONT_DOMAIN = os.environ.get("CloudFrontDomain")
HTML_TO_PDF_FUNCTION = os.environ.get("HTMLtoPDF", "HTMLtoPDF")
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
@app.post("/generateGridsheetPdf")
def generateGridsheetPdf():
    body = app.current_event.json_body or {}
    week = body.get("week") or getCurrentWeek()
    result = generate_gridsheet_pdf(week)
    return {"statusCode": 200, "body": json.dumps({"result": result})}


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

    try:
        pdf_result = generate_gridsheet_pdf(current_week)
        logging.info(f"Gridsheet PDF generated: {pdf_result}")
    except Exception as e:
        logging.exception(f"Error generating gridsheet PDF: {e}")
        # Non-fatal — pool is already closed, just log it

    return {"statusCode": 200, "body": json.dumps({"status": "success", "message": f"Pool closed for week {current_week}"})}


def generate_gridsheet_pdf(week):
    dynamodb = boto3.resource("dynamodb")

    schedule = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME).query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("Week").eq(week)
    ).get("Items", [])

    picks_response = dynamodb.Table(FBP_PICKS_TABLE_NAME).scan(
        FilterExpression=boto3.dynamodb.conditions.Attr("week").eq(week)
    )
    all_picks = picks_response.get("Items", [])
    while "LastEvaluatedKey" in picks_response:
        picks_response = dynamodb.Table(FBP_PICKS_TABLE_NAME).scan(
            FilterExpression=boto3.dynamodb.conditions.Attr("week").eq(week),
            ExclusiveStartKey=picks_response["LastEvaluatedKey"]
        )
        all_picks.extend(picks_response.get("Items", []))

    users_table = dynamodb.Table(USERS_TABLE_NAME)
    user_picks = []
    for item in all_picks:
        email = item.get("email")
        if email:
            user = users_table.get_item(Key={"email": email}).get("Item", {})
            if user.get("userType") == "user":
                user_picks.append(item)
    user_picks.sort(key=lambda x: (x.get("displayName") or "").lower())

    domain = f"https://{CLOUDFRONT_DOMAIN}" if CLOUDFRONT_DOMAIN else "https://my-fbp.com"

    rows_html = ""
    for user_pick in user_picks:
        picks_str = str(user_pick.get("picks", ""))
        team_names = []
        for i, code in enumerate(picks_str):
            game = schedule[i] if i < len(schedule) else None
            if game and code == "H":
                team_names.append(game["Home"])
            elif game and code == "A":
                team_names.append(game["Away"])
            else:
                team_names.append(code)

        picks_cells = "".join(
            f'<img src="{domain}/images/{t}.gif" alt="{t}" style="width:30px;height:30px;" />'
            for t in team_names
        )
        rows_html += (
            f"<tr>"
            f"<td>{user_pick.get('displayName', '')}</td>"
            f"<td>{picks_cells}</td>"
            f"<td>{user_pick.get('tieBreaker', '')}</td>"
            f"</tr>"
        )

    html = f"""<!doctype html><html><head><meta charset="UTF-8">
<style>
  body {{ font-family: sans-serif; }}
  table {{ border-collapse: collapse; margin: auto; }}
  th, td {{ border: 1px solid #ccc; padding: 4px 8px; }}
  img {{ width: 30px; height: 30px; }}
</style></head>
<body>
<h2 style="text-align:center">FBP Week {week} Gridsheet</h2>
<table><thead><tr><th>Name</th><th>Picks</th><th>TB</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""
    year=os.environ.get("YEAR", "2026")
    filename = f"gridsheet_week_{week}_{year}.pdf"
    payload = json.dumps({"html": html, "filename": filename, "base_url": domain})
    powertools_event = {
        "version": "2.0",
        "routeKey": "POST /htmlToPdf",
        "rawPath": "/htmlToPdf",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": payload,
        "requestContext": {
            "routeKey": "POST /htmlToPdf",
            "stage": "$default",
            "requestId": "local-request-id",
            "apiId": "local",
            "http": {
                "method": "POST",
                "path": "/htmlToPdf",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "sam-local",
            },
        },
        "isBase64Encoded": False,
    }
    response = boto3.client("lambda").invoke(
        FunctionName=HTML_TO_PDF_FUNCTION,
        InvocationType="RequestResponse",
        Payload=json.dumps(powertools_event),
    )
    result = json.loads(response["Payload"].read())
    logging.info(f"HTMLtoPDF result: {result}")
    return result


@tracer.capture_lambda_handler
def lambda_handler(event, context) -> dict[str, Any]:
    logging.info(f"Received event: {event}")
    logger.info("ccs was here!")
    return app.resolve(event, context)
