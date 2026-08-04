import json
import os
import random
import re
import boto3
import logging
import hashlib
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logger = logging.getLogger()
logger.info("Initializing GetWeeklyResults Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)


def normalize_phone_number(phone_number):
    digits_only = re.sub(r"\D", "", str(phone_number or ""))
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    if len(digits_only) == 11 and digits_only.startswith("1"):
        return f"+{digits_only}"
    return f"+{digits_only}"


def get_twilio_client_and_sender():
    secret_arn = os.environ.get("TWILIO_CREDENTIALS_SECRET_ARN")
    if not secret_arn:
        raise ValueError("TWILIO_CREDENTIALS_SECRET_ARN is not configured")

    secrets_client = boto3.client("secretsmanager")
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret_payload = json.loads(response["SecretString"])

    account_sid = secret_payload.get("TWILIO_ACCOUNT_SID")
    auth_token = secret_payload.get("TWILIO_AUTH_TOKEN")
    sender_number = secret_payload.get("TWILIO_PHONE_NUMBER")

    if not account_sid or not auth_token or not sender_number:
        raise ValueError("Twilio secret is missing one or more required keys")

    return Client(account_sid, auth_token), sender_number


def send_verification_sms(mobile_number, verification_code):
    sms_client, sender_number = get_twilio_client_and_sender()
    recipient = normalize_phone_number(mobile_number)

    sms_body = (
        f"Your FBP verification code is {verification_code}. "
        "This code expires when you request a new one."
    )

    message = sms_client.messages.create(
        body=sms_body,
        from_=sender_number,
        to=recipient,
    )
    logger.info(f"Verification SMS sent. SID: {message.sid}, To: {recipient}")

@app.post("/storeSMSVerificationCode")
def storeVerificationCode():

    ##
    # get the mobile number from the event body
    ##
    event_body = app.current_event.json_body
    email=event_body.get("email")
    if email is None:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Email is required'}),
        }
    mobile_number = event_body.get("mobile_number")
    if mobile_number is None:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': '10 Digit Mobile number is required'}),
        }
    ##
    # length of mobile_number should be 10
    ##
    if len(mobile_number) != 10:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Mobile number must be 10 digits'}),
        }
    
    ##
    # generate a 6 digit random number
    ##

    verification_code = random.randint(100000, 999999)
    logger.info("Generated SMS verification code")
    ##
    # Convert verification_code to string
    ##
    verification_code = str(verification_code)

    ##
    # Generate a hash of the verification_code
    ##

    verification_code_hash = hashlib.sha256(verification_code.encode()).hexdigest()
    logger.info("Generated SMS verification code hash")

    ##
    # Store pending mobile number and verification code hash in DynamoDB
    ##
    try:
        dynamodb = boto3.resource('dynamodb')
        FBP_USERS_TABLE=os.environ.get('FBPUsersTableName')
        usersTable = dynamodb.Table(FBP_USERS_TABLE)
        usersTable.update_item(
            Key={'email': email},
            UpdateExpression="SET mobile_number = :mobile_number, verification_code = :verification_code, verification_code_hash = :verification_code_hash, sms_verification_status = :sms_verification_status",
            ExpressionAttributeValues={
                ':mobile_number': mobile_number,
                ':verification_code': verification_code,
                ':verification_code_hash': verification_code_hash,
                ':sms_verification_status': 'PENDING'
            }
        )

        send_verification_sms(mobile_number, verification_code)

        return {
            'statusCode': 200,
            'body': json.dumps({'verification_code_hash': verification_code_hash}),
        }
    except (TwilioRestException, ValueError, ClientError) as e:
        logger.error(f"Failed to send SMS verification code: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not send verification code', 'error': str(e)}),
        }
    except Exception as e:

        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not store verification code', 'error': str(e)}),
        }


@app.post("/getSMSVerificationCode")
def getVerificationCode():

    ##
    # get the mobile number from the event body
    ##
    event_body = app.current_event.json_body
    email=event_body.get("email")
    if email is None:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Email is required'}),
        }
    ## Get the verification_code_hash for the given email
    ##
    try:
        dynamodb = boto3.resource('dynamodb')
        FBP_USERS_TABLE=os.environ.get('FBPUsersTableName')
        usersTable = dynamodb.Table(FBP_USERS_TABLE)
        response = usersTable.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        ##
        # if reponse is an empty array, it's an error
        ##
        if not response['Items']:
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'No verification code hash found for this email'}),
            }
        verification_code_hash = response['Items'][0]['verification_code_hash']
        if verification_code_hash is None:
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'No verification code hash found for this email'}),
            }
        return {
            'statusCode': 200,
            'body': json.dumps({'verification_code_hash': verification_code_hash}),
        }
    except Exception as e:

        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not retrieve verification code', 'error': str(e)}),
        }



##
# When you call this, you've already matched the hashes
# This gets called when they have matched, so just update the
# record with the email address provided.
##
@app.post("/updateSMSVerification")
def updateSMSVerification():
    event_body = app.current_event.json_body
    email = event_body.get("email")
    logger.info(f"Updating SMS verification status for email: {email}")
    if email is None:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Email is required'}),
        }
    try:
        dynamodb = boto3.resource('dynamodb')
        FBP_USERS_TABLE = os.environ.get('FBPUsersTableName')
        usersTable = dynamodb.Table(FBP_USERS_TABLE)
        response = usersTable.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        if not response['Items']:
            logger.info(f"No user found for email: {email}")
            return {
                'statusCode': 500,
                'body': json.dumps({'message': 'No user found for this email'}),
            }
        # Update the user record to mark the verification as complete
        usersTable.update_item(
            Key={'email': email},
            UpdateExpression="SET sms_verification_status = :val",
            ExpressionAttributeValues={':val': 'VERIFIED'}
        )
        logger.info(f"SMS verification status updated to 'VERIFIED' successfully for email: {email}")
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'SMS verification updated successfully'}),
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Could not validate verification code', 'error': str(e)}),
        }

def lambda_handler(event, context):
    return app.resolve(event, context)  