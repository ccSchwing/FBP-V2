import boto3
import json
import os
import logging
from botocore.exceptions import ClientError
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig

logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger()
logger.info("Initializing OpenPool Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,
    allow_credentials=False,
)
app = APIGatewayHttpResolver(cors=cors_config)
logger.info("OpenPool Lambda function initialized successfully")

lambda_client = boto3.client("lambda")

FBP_SCHEDULE_TABLE_NAME = os.environ.get("FBPScheduleTableName", "FBP-Schedule")
CLOUDFRONT_DOMAIN = os.environ.get("CloudFrontDomain")
HTML_TO_PDF_FUNCTION = os.environ.get("HTMLtoPDF", "HTMLtoPDF")

# This lamdda function is responsible for all of the work needed to figure out who
# won for the week.
# Step 0:  Make sure the pool is closed for the week that just ended.
# If it is still open, log an error and bail.  We don't want to calculate results while the pool is still open.
# (This should have already been done by the SetPoolStatusClose Lambda, but we can be extra sure here.)
# Calculate the weekly NFL results
# Update the weekly results in the database, including wins/losses for each user and determining the weekly winner.
# Open the pool for the next week.
# Send out the weekly results email to all users.
# That should do it.  : -)
def generate_picksheet_pdf(week):
    schedule = boto3.resource("dynamodb").Table(FBP_SCHEDULE_TABLE_NAME).query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("Week").eq(week)
    ).get("Items", [])

    domain = f"https://{CLOUDFRONT_DOMAIN}" if CLOUDFRONT_DOMAIN else "https://my-fbp.com"

    rows_html = ""
    for i, game in enumerate(schedule):
        away, home = game.get("Away", ""), game.get("Home", "")
        spread = game.get("Spread", "")
        underdog = game.get("Underdog", "")
        away_spread = f"+{spread}" if underdog == "A" else f"-{spread}" if spread else ""
        home_spread = f"+{spread}" if underdog == "H" else f"-{spread}" if spread else ""
        row_class = "game-even" if i % 2 == 0 else "game-odd"
        rows_html += (
            f'<tr class="{row_class}">'
            f'<td><input type="checkbox" name="game{i}" value="A"></td>'
            f'<td><img src="{domain}/images/{away}.gif" style="width:20px;height:20px;"> {away} {away_spread}</td>'
            f'<td><img src="{domain}/images/{home}.gif" style="width:20px;height:20px;"> {home} {home_spread}</td>'
            f'<td><input type="checkbox" name="game{i}" value="H"></td>'
            f"</tr>"
        )

    html = f"""<!doctype html><html><head><meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; font-size: 9px; color: #000; background: #fff; margin: 0.5cm; }}
  table {{ border-collapse: collapse; width: auto; }}
  th {{ background-color: #4caf50; color: #fff; padding: 3px 8px; text-align: center; }}
  td {{ padding: 2px 6px; text-align: center; vertical-align: middle; border-bottom: 1px solid #e0e0e0; }}
  tr.game-even td {{ background-color: #f9f9f9; }}
  tr.game-odd td {{ background-color: #fff; }}
  img {{ width: 20px; height: 20px; }}
</style></head>
<body>
<h2 style="text-align:center">FBP Week {week} Pick Sheet</h2>
<table><thead><tr><th>Pick</th><th>Away</th><th>Home</th><th>Pick</th></tr></thead>
<tbody>{rows_html}</tbody></table>
</body></html>"""

    year = os.environ.get("Year")
    filename = f"picksheet_week_{week}_{year}.pdf"
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

@app.get("/openPool")
def openPool():
    try:
        open_pool_status_check()
        invoke_import_spreads_and_final_scores()
        invoke_calc_weekly_results()
        invoke_update_weekly_results()
        invoke_advanced_messaging_service()
        import_spreads_and_final_scores_for_new_week()
        set_pool_open()
        try:
            week = getCurrentWeek()
            pdf_result = generate_picksheet_pdf(week)
            logging.info(f"Picksheet PDF generated: {pdf_result}")
        except Exception as e:
            logging.exception(f"Error generating picksheet PDF: {e}")  # Non-fatal
    except RuntimeError as e:
        logging.error(f"openPool halted: {e}")
        fbpLog("fbpadmin@my-fbp.com", "openPool", f"openPool halted: {e}", "ERROR")
        return {"statusCode": 500, "body": json.dumps({"status": "error", "message": str(e)})}

def open_pool_status_check():
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
                raise RuntimeError(f"Pool is still open for week {current_week}. Cannot proceed with opening the pool for the new week.")
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
            raise RuntimeError(f"Configuration for current week {current_week} not found.")

    except ClientError as e:
        logging.exception(f"Error checking pool status for week {current_week}: {e}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "OpenPool",
            f"Error checking pool status for week {current_week}: {e}",
            "ERROR",
        )
        raise RuntimeError(f"Error checking pool status for week {current_week}: {e}")

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
def invoke_import_spreads_and_final_scores():
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
        raise RuntimeError(f"ImportSpreadsAndFinalScores failed with status code: {response.get('StatusCode')}")
def invoke_calc_weekly_results():
    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /calcWeeklyResults",
        "rawPath": "/calcWeeklyResults",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "data": app.current_event.raw_event.get("data", {}),
                "parent_request_id": app.lambda_context.aws_request_id,
                "timestamp": app.current_event.raw_event.get("timestamp"),
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
            raise RuntimeError(f"Calc Weekly Results failed with status code: {result.get('statusCode')}")
    except (ClientError, Exception) as e:
        raise RuntimeError(f"Error invoking Calc Weekly Results Lambda: {e}")


    # Next, UpdateWeeklyResults -- this one will update the user's wins/losses and determine the
    # weekly winner.
def invoke_update_weekly_results():
    powertools_event = {
        "version": "2.0",
        "routeKey": "GET /updateWeeklyResults",
        "rawPath": "/updateWeeklyResults",
        "rawQueryString": "",
        "headers": {"content-type": "application/json"},
        "body": json.dumps(
            {
                "data": app.current_event.raw_event.get("data", {}),
                "parent_request_id": app.lambda_context.aws_request_id,
                "timestamp": app.current_event.raw_event.get("timestamp"),
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
            raise RuntimeError(f"UpdateWeeklyResults failed with status code: {result.get('statusCode')}")
    except (ClientError, Exception) as e:
        raise RuntimeError(f"Error invoking UpdateWeeklyResults Lambda: {e}")

    ## Call AdvancedMessagingService Lambda to send out the picksheet notification to
    # subscribed users.
def invoke_advanced_messaging_service():
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
        raise RuntimeError(f"SendMessage (sms/picksheet) failed: {result.get('error')}")

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
    result = json.loads(response["Payload"].read())
    if not result.get("success"):
        raise RuntimeError(f"SendMessage (email/picksheet) failed: {result.get('error')}")

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
        raise RuntimeError(f"SendMessage (sms/weeklywinner) failed: {result.get('error')}")

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
        raise RuntimeError(f"SendMessage (email/weeklywinner) failed: {result.get('error')}")

    logging.info(f"SendMessage Response: {response}")
    fbpLog(
        "fbpadmin@my-fbp.com", "openPool", f"SendMessage Response: {response}", "INFO"
        )
    ##
    # Call the ImportSpreadsAndFinalScores Lambda to import the spreads and final scores for the new week.
    # This will allow the spreads and final scores to be in place by the time the users
    # start making their picks for the new week.
    ##
def set_pool_open():
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
        raise RuntimeError(f"SetPoolStatusOpen failed with status code: {response.get('StatusCode')}")
        ##
    ##
    # Call the ImportSpreadsAndFinalScores Lambda to import the spreads for the new week.
    # This will allow the spreads to be in place by the time the users
    # start making their picks for the new week.
    ##
def import_spreads_and_final_scores_for_new_week():
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
        raise RuntimeError(f"ImportSpreadsAndFinalScores (new week) failed with status code: {response.get('StatusCode')}")

@app.post("/generatePicksheetPdf")
def generatePicksheetPdf():
    body = app.current_event.json_body or {}
    week = body.get("week") or getCurrentWeek()
    result = generate_picksheet_pdf(week)
    return {"statusCode": 200, "body": json.dumps({"result": result})}


def lambda_handler(event, context):
    return app.resolve(event, context)
