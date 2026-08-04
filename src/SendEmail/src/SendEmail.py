from ast import List
import email
import json
import os
from typing import Any, Dict
from urllib import request
import boto3
import logging
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

"""
This function will return all email addresses and displayname for the users in the FBP-Users DynamoDB table.
That data will be used by admin to view/modify profiles for users in the system.
This is GET with no parameters, it will return all users in the system with their email and display name.
"""
logging.basicConfig(format="%(levelname)s %(message)s")
logger = logging.getLogger("SendEmail")
logger.info("Initializing SendEmail Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)
logger.info(
    "SendEmail Lambda function initialized successfully"
)  # Log successful initialization


USERS_TABLE_NAME = os.environ.get("FBPUsersTableName", "FBP-Users")
logger.info(f"Using DynamoDB table: {USERS_TABLE_NAME}")
fbpLog("fbpadmin@my-fbp.com", "SendEmail", "Lambda function initialized", "INFO")

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


#  THe function below is the main logic for the lambda function.
#  It will parse the email address from the event and then call
#  the getFBPUserData function to get the user information from DynamoDB.
#  Finally, it will return the user information in the response.
@app.post("/sendEmail")  # This is the endpoint for OPTIONS
def sendTemplatedEmail():
    logger.info("Handling sendTemplatedEmail request")  # Log entry into the function
    try:
        logger.info(
            f"Raw event data: {json.dumps(app.current_event.raw_event, default=str)}"
        )  # Log the raw event data

    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "SendEmail", f"Unexpected error: {e}", "ERROR")
        logger.error(f"Unexpected error: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "error": f"exception occurred: {e}",
                    "message": "An unexpected error occurred while processing the request",
                }
            ),
        }
    # Get the request body and see what the request is for.
    body = app.current_event.json_body
    # instead of passing the email target, querying the FBP-Users
    # to get the email addresses that have signed up for the particular template.
    # For New Users, we NEED the email address. So:
    ## Not needed here email=body.get('email')
    # If email is None, it's okay because the other templates don't require the email address to be passed in.
    # They will pull the email address from the FBP-Users table based on the template they are signed up for.
    #  But for the WelcomeEmailTemplate, we need the email address to send the welcome email to the new user. So if the template is WelcomeEmailTemplate and the email is None, we will return an error message.
    ## Not needed here firstName=body.get('firstName')

    # You should check to see if the template is in SES, if not return an error message.
    templateName = body.get("templateName")

    logger.info(f"the templateName is: {templateName}")
    if not templateName:
        fbpLog(
            "fbpadmin@my-fbp.com",
            "SendEmail",
            "templateName not present:  Please provide a valid request type (email, firstName, messageType)",
            "ERROR",
        )
        return {
            "statusCode": 400,
            "body": json.dumps(
                {
                    "error": "Invalid request type",
                    "message": "templateName not present:  Please provide a valid request type (email, firstName, messageType)",
                }
            ),
        }

    items = []
    params = dict[str, Any]()
    match templateName:
        case "WelcomeEmailTemplate":
            logger.info("Processing request for Welcome Email")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "GetFBPUser",
                "Processing request for Welcome Email",
                "INFO",
            )
            email = body.get("email")
            firstName = body.get("firstName")
            params = {
                "email": email,
                "firstName": firstName,
                "templateName": templateName,
            }
            items = sendEmailWithTemplate(params)
        case "PickSheetTemplate":
            logger.info("Processing request for picks sheet")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "GetFBPUser",
                "Processing request for picks sheet",
                "INFO",
            )
            table = boto3.resource("dynamodb").Table(USERS_TABLE_NAME)
            emailAddrs = table.scan(ProjectionExpression="email, firstName")
            FilterExpression = boto3.dynamodb.conditions.Attr("emailPickSheet").eq(True)
            if emailAddrs:
                emailAddrs = table.scan(
                    ProjectionExpression="email, firstName",
                    FilterExpression=FilterExpression,
                )["Items"]
                for addr in emailAddrs:
                    email = addr.get("email")
                    firstName = addr.get("firstName")
                    params = {
                        "email": email,
                        "firstName": firstName,
                        "templateName": templateName,
                    }
                    fbpLog(
                        email,
                        "SendEmail",
                        f"Sending picks sheet email to: {email}",
                        "INFO",
                    )
                    logger.info(
                        f"Sending picks sheet email to: {email} with template: {templateName}"
                    )  #
                    items = sendEmailWithTemplate(params=params)
        case "FBPWeeklyWinner":
            logger.info("Processing request for weekly winner")
            # Get the winner display name from FBP-Users table
            fbpLog(
                "fbpadmin@my-fbp.com",
                "SendEmail",
                "Processing request for weekly winner",
                "INFO",
            )
            usersTable = boto3.resource("dynamodb").Table(USERS_TABLE_NAME)
            week = getCurrentWeek()
            # query the FBP-Weekly-Results-2025 table for winner=true
            FBPWeeklyResultsTableName = os.environ.get(
                "FBPWeeklyResults2025TableName", "FBP-Weekly-Results-2025"
            )
            resultsTable = boto3.resource("dynamodb").Table(FBPWeeklyResultsTableName)
            winner = resultsTable.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("week").eq(week)
                & boto3.dynamodb.conditions.Attr("winner").eq(True),
                ProjectionExpression="email, #wins, week",
                ExpressionAttributeNames={"#wins": "correctpicks"},
            )["Items"]

            #
            # winner= resultsTable.scan(FilterExpression=boto3.dynamodb.conditions.Attr('winner').eq(True))['Items']
            # Use winner email address to get display name from FBP-Users
            winnerInfo = usersTable.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr("email").eq(
                    winner[0].get("email")
                )
            )["Items"]
            winnerDisplayName = winnerInfo[0].get("displayName")
            params = {
                "email": "Dummy Value",
                "firstName": "Dummy Value",
                "winnerDisplayName": winnerDisplayName,
                "wins": int(winner[0].get("correctpicks")),
                "templateName": templateName,
                "week": week,
            }
            debug = False
            if debug:
                params = {
                    "email": "chuckschwing@proton.me",
                    "firstName": "Chuck",
                    "winnerDisplayName": winnerDisplayName,
                    "wins": int(winner[0].get("correctpicks")),
                    "templateName": templateName,
                    "week": week,
                }
                items = sendEmailWithTemplate(params=params)
                logger.info(f"items: {items}")
                logger.info(
                    f"Debug mode is on, sending email to: {params.get('email')} with template: {templateName}"
                )
            # Get all email address and send to them
            else:
                emailaddrs = usersTable.scan(ProjectionExpression="email, firstName")["Items"]
                for addr in emailaddrs:
                    logger.info(
                        f"Sending weekly winner email to: {addr.get('email')} with winner display name: {winnerDisplayName}"
                    )  # Log the email and template being used
                    fbpLog(
                        addr.get("email"),
                        "SendEmail",
                        f"Sending weekly winner email to: {addr.get('email')} with winner display name: {winnerDisplayName}",
                        "INFO",
                    )
                    params["email"] = addr.get("email")
                    params["firstName"] = addr.get("firstName")
                    items = sendEmailWithTemplate(params=params)
        case "BetaTestTemplate":
            logger.info("Processing request for beta test")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "GetFBPUser",
                "Processing request for beta test",
                "INFO",
            )
            table = boto3.resource("dynamodb").Table(USERS_TABLE_NAME)
            emailAddrs = table.scan(ProjectionExpression="email, firstName")
            FilterExpression = boto3.dynamodb.conditions.Attr("beta").eq(True)
            if emailAddrs:
                emailAddrs = table.scan(
                    ProjectionExpression="email, firstName",
                    FilterExpression=FilterExpression,
                )["Items"]
                for addr in emailAddrs:
                    email = addr.get("email")
                    firstName = addr.get("firstName")
                    params = {
                        "email": email,
                        "firstName": firstName,
                        "templateName": templateName,
                    }
                    items = sendEmailWithTemplate(params=params)

        case "GridSheetTemplate":
            logger.info("Processing request for grid sheet")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "GetFBPUser",
                "Processing request for gridsheet",
                "INFO",
            )
            table = boto3.resource("dynamodb").Table(USERS_TABLE_NAME)
            logger.info(
                f"Scanning DynamoDB table: {USERS_TABLE_NAME} for users with emailGridSheet set to True"
            )
            emailAddrs = table.scan(ProjectionExpression="email, firstName")
            FilterExpression = boto3.dynamodb.conditions.Attr("emailGridSheet").eq(True)
            if emailAddrs:
                emailAddrs = table.scan(
                    ProjectionExpression="email, firstName",
                    FilterExpression=FilterExpression,
                )["Items"]
                for addr in emailAddrs:
                    email = addr.get("email")
                    firstName = addr.get("firstName")
                    params = {
                        "email": email,
                        "firstName": firstName,
                        "templateName": templateName,
                    }
                    fbpLog(
                        email,
                        "SendEmail",
                        f"Sending grid sheet email to: {email}",
                        "INFO",
                    )
                    logger.info(
                        f"Sending grid sheet email to: {email} with template: {templateName}"
                    )  #
                    items = sendEmailWithTemplate(params=params)
        case "ReminderEmailTemplate":
            logger.info("Processing request for reminders")
            fbpLog(
                "fbpadmin@my-fbp.com",
                "GetFBPUser",
                "Processing request for reminders",
                "INFO",
            )
            table = boto3.resource("dynamodb").Table(USERS_TABLE_NAME)
            logger.info(
                f"Scanning DynamoDB table: {USERS_TABLE_NAME} for users with emailReminders set to True"
            )
            emailAddrs = table.scan(ProjectionExpression="email, firstName")
            FilterExpression = boto3.dynamodb.conditions.Attr("emailReminders").eq(True)
            if emailAddrs:
                emailAddrs = table.scan(
                    ProjectionExpression="email, firstName",
                    FilterExpression=FilterExpression,
                )["Items"]
                for addr in emailAddrs:
                    email = addr.get("email")
                    firstName = addr.get("firstName")
                    params = {
                        "email": email,
                        "firstName": firstName,
                        "templateName": templateName,
                    }
                    items = sendEmailWithTemplate(params=params)
        case _:
            logger.error("Invalid request type")
            fbpLog("fbpadmin@my-fbp.com", "GetFBPUser", "Invalid request type", "ERROR")
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {
                        "error": "Invalid request type",
                        "message": "Please provide a valid template name.",
                    }
                ),
            }

    # If items is empty return it anyway
    if items:
        logger.info(f"MessageIDs returned: {items}")  # Log the items being returned
        return {"statusCode": 200, "body": json.dumps({"items": items})}


def sendEmailWithTemplate(params):
    logger.info(f"TemplateData being sent: {json.dumps(params)}")
    email = params.get("email")
    firstName = params.get("firstName")
    templateName = params.get("templateName")
    logger.info(
        f"Sending email to: {email} and firstName: {firstName} with template: {templateName}"
    )  # Log the email and template being used
    fbpLog(
        email,
        "SendEmail",
        f"Sending email to: {email} and firstName: {firstName} with template: {templateName}",
        "INFO",
    )
    ses = boto3.client("ses", region_name="us-east-1")
    try:
        response = ses.send_templated_email(
            Source="fbpadmin@my-fbp.com",
            Destination={
                "ToAddresses": [
                    email,
                ],
            },
            Template=templateName,
            TemplateData=json.dumps(params),
        )
        return response
    except ClientError as e:
        logger.exception(f"Simple Mail Service Error: {e}")
        fbpLog(
            "fbpadmin@my-fbp.com",
            "sendEmail",
            f"Simple Mail Service Error: {e}",
            "ERROR",
        )
        return None
    except Exception as e:
        fbpLog(
            "fbpadmin@my-fbp.com",
            "sendEmail",
            f"Unexpected Simple Mail Service error: {e}",
            "ERROR",
        )
        logger.exception(f"Unexpected error: {e}")
        return None


def lambda_handler(event, context):
    return app.resolve(event, context)
