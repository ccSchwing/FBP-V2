from calendar import week
import json
from multiprocessing import pool
import re
import boto3
import logging
from decimal import Decimal
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.getCurrentWeek import getCurrentWeek
from fbplib.fbpLog import fbpLog


logger = logging.getLogger()
logger.info("Initializing GetPoolOpenEvent Lambda function")  # Log initialization message
fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", "Initializing GetPoolOpenEvent Lambda function", "INFO")
logger.setLevel(level=logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)
logger.info("CORS configuration applied")

@app.get("/getPoolOpen")
@app.get("/getPoolStatus")
def getPoolStatus():
    """
    Lambda function to retrieve poolOpen Boolean value from FBP-Config table
    Will be used by most end user pages to determine whether they can do certain things.
    """
    
    # Initialize DynamoDB resource
    logger.info("Connecting to DynamoDB table FBP-Config")
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('FBP-Config')
    try:
        week_number = getCurrentWeek()
        if week_number is None:
            fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", "Cannot determine current week.", "ERROR")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Cannot determine current week.',
                    'message': 'Check logs for errors.',
                    'pool_open': False
                })
            }
        
        # Convert to integer if it's a string
        try:
            week_number = int(week_number)
        except (ValueError, TypeError):
            fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", "Invalid week number.", "ERROR")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid week number',
                    'message': 'Week must be a valid number',
                    'pool_open': False
                })
            }
        
        # Query DynamoDB table
        response = table.get_item(
            Key={
                'Week': week_number
            }
        )
        
        # Check if item exists and return poolOpen value
        if 'Item' in response:
            pool_open = response['Item'].get('poolOpen', False)
            if pool_open == True:
                logger.info(f"Week {week_number} pool is OPEN")
                fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", f"Week {week_number} pool is OPEN", "INFO")
            else:
                logger.info(f"Week {week_number} pool is CLOSED")
                fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", f"Week {week_number} pool is CLOSED", "INFO")
            week_number = response['Item'].get('Week', week_number)            
            if isinstance(week_number, Decimal):
                week_number = int(week_number)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'week': week_number,
                    'pool_open': pool_open
                })
            }
        else:
            fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", f"Configuration for week {week_number} not found", "ERROR")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'Configuration for week {week_number} not found',
                    'week': week_number,
                    'pool_open': False
                })
            }
            
    except ClientError as e:
        fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", f"Database error: {str(e)}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Database error',
                'details': str(e)
            })
        }
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "GetPoolOpenEvent", f"Unexpected error: {str(e)}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }

def lambda_handler(event, context):
    return app.resolve(event, context)