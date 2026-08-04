import os
import json
import boto3
import logging
from botocore.exceptions import ClientError
from decimal import Decimal
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.getCurrentWeek import getCurrentWeek
from fbplib.fbpLog import fbpLog


logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing GetStandings Lambda function")  # Log initialization message
logger.setLevel(level=logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)
logger.info("CORS configuration applied")

app=APIGatewayHttpResolver(cors=cors_config)
@app.get("/getStandings")
def getStandings():
    """
    Lambda function to scan FBP-Users table and return year to date wins, losses and DisplayName
    """
    
    # Initialize DynamoDB resource
    logger.info("Connecting to DynamoDB table FBP-Config")
    dynamodb = boto3.resource('dynamodb')
    USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
    table = dynamodb.Table(USERS_TABLE_NAME)
    try:
        week_number = getCurrentWeek()
        if week_number is None:
            fbpLog("fbpadmin@my-fbp.com", "GetStandings", "Cannot determine week.", "ERROR")
            logger.error("Cannot determine week.")
            return Response (
                status_code=400,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Cannot determine current week.',
                    'message': 'Check logs for errors.'
                })
            )
        
        # Convert to integer if it's a string
        try:
            week_number = int(week_number)
        except (ValueError, TypeError):
            fbpLog("fbpadmin@my-fbp.com", "GetStandings", "Invalid week number.", "ERROR")
            logger.error("Invalid week number.")
            return Response (
                status_code=400,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Invalid week number',
                    'message': 'The week number could not be converted to an integer.'
                })
            )
        
        try:
            logger.info(f"Scanning DynamoDB table {USERS_TABLE_NAME} for users of type 'user'")
            response = table.scan(
                FilterExpression=boto3.dynamodb.conditions.Attr('userType').eq('user')
            )
            logger.info(f"Retrieved data from DynamoDB: {response}")
            items = response.get('Items', [])
            logger.info(f"Items retrieved: {items}")
            items.sort(key=lambda x: x.get('totalCorrectPicks', Decimal(0)), reverse=True)

            fbpLog("fbpadmin@my-fbp.com", "GetStandings", "Retrieved Standings","INFO")
            return Response (
                status_code=200,
                content_type="application/json",
                body=json.dumps(items, default=lambda x: int(x) if isinstance(x, Decimal) else str(x))
            )
        except ClientError as e:
            fbpLog("fbpadmin@my-fbp.com", "GetStandings", f"Exception: {e}","ERROR")
            logger.error(f"DynamoDB Error: {e}")
            return Response (
                500,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Database error',
                    'details': str(e)
                })
            )
        except Exception as e:
            fbpLog("fbpadmin@my-fbp.com", "GetStandings", f"Exception: {e}","ERROR")
            logger.error(f"Unexpected error: {e}")

            return Response (
                status_code=500,
                content_type="application/json",
                body=json.dumps({
                    'error': 'Internal server error',
                    'message': str(e)
                })
            )
        
    except ClientError as e:
        fbpLog("fbpadmin@my-fbp.com", "GetStandings", f"ClientError: {e}", "ERROR")
        logger.error(f"ClientError: {e}")
        return Response (
            status_code=500,
            content_type="application/json",
            body=json.dumps({
                'error': 'Database error',
                'details': str(e)
            })
        )
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "GetStandings", f"Unexpected error: {e}", "ERROR")
        logger.error(f"Unexpected error: {e}")
        return Response (
            status_code=500,
            content_type="application/json",
            body=json.dumps({
                'error': 'Internal server error',
                'message': 'Unable to process request at this time.'
            })
        )

def lambda_handler(event, context):
    return app.resolve(event, context)