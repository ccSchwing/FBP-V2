import json
import boto3
from decimal import Decimal
from botocore.exceptions import ClientError
from fbplib.fbpLog import fbpLog

def lambda_handler(event, context):
    """
    This function will return the week number and the poolOpen Boolean value 
    from FBP-Config table for the given week number in the event.
    """
    item = get_pool_config()
     
        
    # Check if item exists and return poolOpen value
    if item:
        pool_open = item.get('poolOpen', False)
        week_number = item.get('Week', None)
        if isinstance(week_number, Decimal):
            week_number = int(week_number)
        return {
            'statusCode': 200,
            'body': json.dumps({
                'week': week_number,
                'poolOpen': pool_open
                })
            }
    else:
        fbpLog("fbpadmin@my-fbp.com", "GetPoolConfig", "Configuration not found", "ERROR")
        return {
            'statusCode': 404,
            'body': json.dumps({
                'error': f'Configuration not found',
                'week': None,
                'poolOpen': False
                })
            }
            

def get_pool_config():
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('FBP-Config')
    try:
        '''
        There is only one row in FBP-Config.
        '''
        response = table.scan(Limit=1)
        item = response.get('Items')[0] if response.get('Items') else None
        
        
        return item
    except ClientError as e:
        fbpLog("fbpadmin@my-fbp.com", "GetPoolConfig", f"DynamoDB Error: {e}", "ERROR")
        return None
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "GetPoolConfig", f"Unexpected error: {e}", "ERROR")
        return None
