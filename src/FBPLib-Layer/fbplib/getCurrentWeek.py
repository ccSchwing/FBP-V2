import os
import boto3
from decimal import Decimal
from botocore.exceptions import ClientError
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

def getCurrentWeek():
    FBP_CONFIG_TABLE_NAME = os.environ.get('FBPConfigTableName', 'FBP-Config')
    logger.info(f"Fetching current week from DynamoDB table: {FBP_CONFIG_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_CONFIG_TABLE_NAME)
    try:
        response = table.scan()
        items = response.get('Items', [])

        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        if not items:
            logger.error("No configuration found in FBP-Config table.")
            return None

        max_week = None
        for item in items:
            week_number = item.get('Week')
            if isinstance(week_number, Decimal):
                week_number = int(week_number)
            if isinstance(week_number, int) and (max_week is None or week_number > max_week):
                max_week = week_number

        if max_week is None:
            logger.error("No valid Week values found in FBP-Config table.")
            return None

        return max_week
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None
    
