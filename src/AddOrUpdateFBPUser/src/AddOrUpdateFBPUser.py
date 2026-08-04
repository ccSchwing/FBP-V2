import json
import os
import boto3
import logging
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek


'''
This function will update the user information for the given email address in the event.
'''
logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing AddOrUpdateFBPUser Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
logger.info(f"Using DynamoDB table: {USERS_TABLE_NAME}")  # Log the table name being used

PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', 'FBP-Picks')
logger.info(f"Using DynamoDB table: {PICKS_TABLE_NAME}")  # Log the table name being used
fbpLog("fbpadmin@my-fbp.com", "AddOrUpdateFBPUser", f"Using DynamoDB table: {PICKS_TABLE_NAME}", "INFO")

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)


def has_mobile_update_field(request_body):
    if not isinstance(request_body, dict):
        return False
    mobile_keys = ['mobile_number', 'MobileNumber', 'mobileNumber', 'mobile']
    return any(key in request_body for key in mobile_keys)

#  The function below is the main logic for the lambda function.
#  It will parse the email address from the event and then call
#  the updateFBPUserData function to update the user information in DynamoDB.
#  Finally, it will return the updated user information in the response.
@app.post("/updateFBPUser")
def updateFBPUser():
    logger.info("Handling updateFBPUser request")  # Log entry into the function
    try:
        logger.info(f"Raw event data: {json.dumps(app.current_event.raw_event, default=str)}")  # Log the raw event data
        fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"Raw event data: {json.dumps(app.current_event.raw_event, default=str)}", "INFO")
        request_body = app.current_event.json_body
        email = request_body.get('email') if request_body else None
        if not email:
            logger.warning("Email field is missing in the request body")
            fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", "Email field is missing in the request body", "ERROR")
            return Response(
                status_code=400,
                body=json.dumps({
                    'error': 'Email address is required',
                    'message': 'Please provide email address in the event'
                })
            )
        logger.info(f"Extracted email from API Gateway event: {email}")
        logger.info(f"Request body: {request_body}")
        if not request_body:
            logger.error("No JSON body found in the request")
            fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", "No JSON body found in the request", "ERROR")
            return Response(
                status_code=400,
                body=json.dumps({
                    'error': 'Invalid request body',
                    'message': 'Request body seems to be empty or not valid JSON'
                })
            )

        if has_mobile_update_field(request_body):
            message = 'Mobile number updates must be completed through the SMS verification flow before saving profile changes.'
            logger.warning(message)
            fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", message, "WARN")
            return Response(
                status_code=400,
                body=json.dumps({
                    'error': 'Mobile number update requires verification',
                    'message': message,
                    'errorCode': 'MOBILE_VERIFICATION_REQUIRED'
                })
            )

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "AddOrUpdateFBPUser", f"Unexpected error: {e}", "ERROR")
        return Response(
            status_code=400,
            body=json.dumps({
                'error': 'Invalid request body',
                'message': 'Request body must be valid JSON with an email field'
            })
        )

    item = updateFBPUserData(request_body)
    
    if item:
        fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"Updated user data for email: {email}: request_body: {json.dumps(request_body, default=str)}", "INFO")
        response_data = {
            'email': item.get('email'),
            'defaultAlgorithm': item.get('defaultAlgorithm'),
            'defaultTieBreaker': item.get('defaultTieBreaker'),
            'displayName': item.get('displayName'),
            'paymentMethod': item.get('paymentMethod'),
            'emailGridSheet': item.get('emailGridSheet'),
            'emailPickSheet': item.get('emailPickSheet'),
            'emailReminders': item.get('emailReminders'),
            'firstName': item.get('firstName'),
            'lastName': item.get('lastName')
        }
        return Response(
            status_code=200,
            body=json.dumps(response_data)
        )
    else:
        logger.error(f"User not found: {email}")
        fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"User not found: {email}", "ERROR")
        return Response(
            status_code=404,
            body=json.dumps({
                'error': f'User with email {email} not found',
                'email': email,
                })
            ) 



@app.post("/addFBPUser")
def addFBPUser():
    logger.info("Handling addFFBPUser request")  # Log entry into the function
    try:
        logger.info(f"Raw event data: {json.dumps(app.current_event.raw_event, default=str)}")  # Log the raw event data
        request_body = app.current_event.json_body
        email = request_body.get('email') if request_body else None
        if not email:
            logger.warning("Email field is missing in the request body")
            fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", "Email field is missing in the request body", "ERROR")
            return Response(
                status_code=400,
                body=json.dumps({
                    'error': 'Email address is required',
                    'message': 'Please provide email address in the event'
                })
            )
        logger.info(f"Extracted email from API Gateway event: {email}")
        logger.info(f"Request body: {request_body}")
        if not request_body:
            logger.error("No JSON body found in the request")
            fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", "No JSON body found in the request", "ERROR")
            return Response(
                status_code=400,
                body=json.dumps({
                    'error': 'Invalid request body',
                    'message': 'Request body seems to be empty or not valid JSON'
                })
            )

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"Unexpected error: {e}", "ERROR")
        return Response(
            status_code=400,
            body=json.dumps({
                'error': 'Invalid request body',
                'message': 'Request body must be valid JSON with an email field'
            })
        )

    response = addFBPUserData(request_body)
    
    return Response(
        status_code=response.status_code,
        body=response.body)



        

def updateFBPUserData(request_body):
    dynamodb = boto3.resource('dynamodb')  # type: ignore
    table = dynamodb.Table(USERS_TABLE_NAME)
    try:
        response = table.update_item(
            Key={
                'email': request_body.get('email')
            },
            UpdateExpression=
                "SET defaultAlgorithm = :defaultAlgorithm, "
                "displayName = :displayName, "
                "paymentMethod = :paymentMethod, "
                "emailGridSheet = :emailGridSheet, "
                "emailPickSheet = :emailPickSheet, "
                "emailReminders = :emailReminders, "
                "smsReminder = :smsReminder, "
                "smsPickSheet = :smsPickSheet, "
                "smsGridSheet = :smsGridSheet, "
                "firstName = :firstName, "
                "lastName = :lastName, "
                "defaultTieBreaker = :defaultTieBreaker",
            ExpressionAttributeValues={
                ':defaultAlgorithm': request_body.get('defaultAlgorithm'),
                ':defaultTieBreaker': request_body.get('defaultTieBreaker'),
                ':displayName': request_body.get('displayName'),
                ':paymentMethod': request_body.get('paymentMethod'),
                ':emailGridSheet': bool(request_body.get('emailGridSheet')),
                ':emailPickSheet': bool(request_body.get('emailPickSheet')),
                ':emailReminders': bool(request_body.get('emailReminders')),
                ':smsReminder': bool(request_body.get('smsReminder')),
                ':smsPickSheet': bool(request_body.get('smsPickSheet')),
                ':smsGridSheet': bool(request_body.get('smsGridSheet')),
                ':firstName': request_body.get('firstName'),
                ':lastName': request_body.get('lastName')
            },
        )
        # Now update the FBP_PICKS_TABLE_NAME with the new displayName if it has changed.
        pickTable = dynamodb.Table(PICKS_TABLE_NAME)
        try:
            response = pickTable.update_item(
                Key={
                    'email': request_body.get('email')
                },
                UpdateExpression="SET displayName = :displayName",
                ExpressionAttributeValues={
                    ':displayName': request_body.get('displayName')
                }
            )
        except ClientError as e:
            logger.error(f"DynamoDB Error: {e}")
            fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"DynamoDB Error: {e}", "ERROR")
            return None
        # Retrieve the updated item to return
        get_response = table.get_item(Key={'email': request_body.get('email')})
        return get_response.get('Item')
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"DynamoDB Error: {e}", "ERROR")
        return None
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "UpdateFBPUser", f"Unexpected error: {e}", "ERROR")
        logger.error(f"Unexpected error: {e}")
        return None


def addFBPUserData(request_body):
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(USERS_TABLE_NAME)
    ##
    # Check to see ifi the user already exists in the FBP_USERS_TABLE_NAME.  If so, return an error.
    ##
    try:
        existing_user = table.get_item(Key={'email': request_body.get('email')})
        if 'Item' in existing_user:
            return Response(
                status_code=200,
                body=json.dumps({'error': f'User with email {request_body.get("email")} already exists'})
            )
    except ClientError as e:
        logger.exception(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"DynamoDB Error: {e}", "ERROR")
        return Response(
            status_code=500,
            body=json.dumps({'error': f'Failed to check existing user for email {request_body.get("email")}'})
        )
    try:
        response = table.put_item(
            Item={
                'email': request_body.get('email'),
                'defaultAlgorithm': request_body.get('defaultAlgorithm'),
                'defaultTieBreaker': request_body.get('defaultTieBreaker'),
                'displayName': request_body.get('displayName'),
                # paymentMethod is only available when the user is updated.
                # That's why it's not included here.  Admin creates the account.
                'emailGridSheet': bool(request_body.get('emailGridSheet')),
                'emailPickSheet': bool(request_body.get('emailPickSheet')),
                'emailReminders': bool(request_body.get('emailReminders')),
                'firstName': request_body.get('firstName'),
                'lastName': request_body.get('lastName'),
                'isAccountLocked': bool(request_body.get('isAccountLocked')),
                'isAdmin': bool(request_body.get('isAdmin')),
                'userType': request_body.get('userType'),
                'isPaidUser': bool(request_body.get('isPaidUser'))
            }
        )
    except ClientError as e:
        logger.exception(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"DynamoDB Error: {e}", "ERROR")
        return Response(
            status_code=500,
            body=json.dumps({'error': f'Failed to add user data for email {request_body.get("email")}'})
        )
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"Unexpected error: {e}", "ERROR")
        logger.exception(f"Unexpected error: {e}")
        return Response(
            status_code=500,
            body=json.dumps({'error': f'Unexpected error occurred for email {request_body.get("email")}'})
        )

    # Now we need to add the entry into the FBP_PICKS_TABLE_NAME.
    week=getCurrentWeek()
    pickTable = dynamodb.Table(PICKS_TABLE_NAME)
    try:
        response = pickTable.put_item(
            Item={
                'email': request_body.get('email'),
                'displayName': request_body.get('displayName'),
                'week': week,
                'picks': "",
                'tieBreaker': request_body.get('defaultTieBreaker'),
            }
        )
        return Response(
            status_code=200,
            body=json.dumps({
                'email': request_body.get('email'),
                'defaultAlgorithm': request_body.get('defaultAlgorithm'),
                'defaultTieBreaker': request_body.get('defaultTieBreaker'),
                'displayName': request_body.get('displayName'),
                'emailGridSheet': request_body.get('emailGridSheet'),
                'emailPickSheet': request_body.get('emailPickSheet'),
                'emailReminders': request_body.get('emailReminders'),
                'firstName': request_body.get('firstName'),
                'lastName': request_body.get('lastName'),
                'isAccountLocked': request_body.get('isAccountLocked'),
                'isAdmin': request_body.get('isAdmin'),
                'userType': request_body.get('userType'),
                'isPaidUser': request_body.get('isPaidUser')
            })
        )
    except ClientError as e:
        logger.exception(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"DynamoDB Error: {e}", "ERROR")
        return Response(
            status_code=500,
            body=json.dumps({'error': f'Failed to add user picks table entry for email {request_body.get("email")}'})
        )
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "AddFBPUser", f"Unexpected error: {e}", "ERROR")
        logger.exception(f"Unexpected error: {e}")
        return Response(
            status_code=500,
            body=json.dumps({'error': f'Unexpected error occurred for email {request_body.get("email")}'})
        )

def lambda_handler(event, context):
    return app.resolve(event, context)