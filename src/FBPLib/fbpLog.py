import os
import boto3
import datetime
import pytz
from decimal import Decimal
from botocore.exceptions import ClientError
import logging
from fbplib import getCurrentWeek

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

def fbpLog(email, action, details, level, week=None):
    FBP_LOG_TABLE_NAME = os.environ.get('FBPLogsTableName', '2025-Log')
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_LOG_TABLE_NAME)
    pytz_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(pytz_tz).strftime('%Y-%m-%d %H:%M:%S')
    now_est = datetime.datetime.now(pytz_tz).strftime('%m-%d-%Y %H:%M:%S')
    logger.info(f"Logging action: {action} for email: {email} with details: {details} at {now}")
    week=getCurrentWeek.getCurrentWeek() if week is None else week
    # console_log_entry = f"[{now}] [Week {week}] [{level.upper()}] [{email}] {action} - {details}"
    # logger.info(console_log_entry)
    
    log_entry = {
        'email': email,
        'week': week,
        'timestamp': now_est,
        'action': action,
        'details': details,
        'level': level
    }
    try:
        table.put_item(Item=log_entry)
        logger.info(f"Log entry successfully written to DynamoDB: {log_entry}")

    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return None
    
