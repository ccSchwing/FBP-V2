import json
import boto3
import logging
import os
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)


app = APIGatewayHttpResolver(cors=cors_config)


def parse_pool_open(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "y"):
            return True
        if lowered in ("false", "0", "no", "n"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None

# If create_next_week is False, this function will update the poolOpen value for the current week.
# If create_next_week is True, this function will create a new entry for the next week
def _set_pool_status(create_next_week, poolAction, forced_pool_open=None):
    config_table_name = os.environ.get('FBP_CONFIG_TABLE_NAME', 'FBP-Config')
    week_number = None
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(config_table_name)
    try:
        logger.info(f"[poolAction] Entered {poolAction}")
        logger.info(f"[poolAction] raw_path={app.current_event.raw_path}, route_key={app.current_event.request_context.route_key}")

        week_number = getCurrentWeek()
        if week_number is None:
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", "Failed to get current week", "ERROR")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': 'Failed to get current week'})
            }

        poolStatus=table.get_item(Key={'Week': week_number})
        if 'Item' not in poolStatus:
            logger.error(f"Configuration for current week {week_number} not found.")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Configuration for current week {week_number} not found.", "ERROR")
            return {
                'statusCode': 500,
                'body': json.dumps({'error': f'Configuration for current week {week_number} not found'})
            }
        pool_open = poolStatus['Item'].get('poolOpen')
        if pool_open is None:
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", "poolOpen must be a boolean (true/false)", "ERROR")
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'Invalid request',
                    'message': 'poolOpen must be a boolean (true/false)'
                })
            }
        if pool_open == False and poolAction == "setPoolStatusClosed":
            logger.info(f"Pool is already closed, ignoring request to close it again.")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Pool is already closed, ignoring request to close it again.", "INFO")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'error': 'Pool is already closed',
                    'week': week_number,
                    'poolOpen': pool_open
                })
            }
        ##
        # Make sure to preserver the value of resultsCalculated when updating the pool status.
        # We don't want to accidentally reset it to false if it's already true.
        # That would cause the system to think that the results haven't been calculated yet for the week,
        # which could cause issues data integrity issues.
        ##
        currentPoolStatus=table.get_item(Key={'Week': week_number})
        results_calculated = currentPoolStatus['Item'].get('resultsCalculated')

        if pool_open == True and poolAction == "setPoolStatusClosed":
            logger.info(f"Pool is currently open, proceeding to close it.")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Pool is currently open, proceeding to close it.", "INFO")
            if 'Item' not in currentPoolStatus:
                logger.error(f"Configuration for current week {week_number} not found when trying to check resultsCalculated.")
                fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Configuration for current week {week_number} not found when trying to check resultsCalculated.", "ERROR")
                return {
                    'statusCode': 500,
                    'body': json.dumps({'error': f'Configuration for current week {week_number} not found when trying to check resultsCalculated'})
                }
            else:
                next_week_item = {
                'Week': week_number,
                'poolOpen': False,
                'resultsCalculated': results_calculated
            }
    

        # add new record for next week with poolOpen value, week_number + 1, and resultsCalculated = false
        if (create_next_week == True):
            logger.info(f"Creating new entry for next week: {week_number + 1}")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Creating new entry for next week: {week_number + 1}", "INFO")
            next_week_item = {
                'Week': week_number + 1,
                'poolOpen': True,
                'resultsCalculated': False
            }
            try:
                newPoolOpenValue=True
                table.put_item(Item=next_week_item)
                logger.info(f"Created new entry for next week: {week_number + 1} with poolOpen={newPoolOpenValue}")
                fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Created new entry for next week: {week_number + 1} with poolOpen={newPoolOpenValue}", "INFO")
            except ClientError as error:
                logger.error(f"Error creating entry for next week: {error}")
                fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Error creating entry for next week: {error}", "ERROR")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Database error',
                        'details': str(error)})
                }
        if (create_next_week == False):
            logger.info(f"Updating poolOpen value for week {week_number} to: {forced_pool_open}")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Updating poolOpen value for week {week_number} to: {forced_pool_open}", "INFO")
            newPoolOpenValue=False
            next_week_item = {
                'Week': week_number,
                'poolOpen': newPoolOpenValue,
                'resultsCalculated': results_calculated
            }
            try:
                table.put_item(Item=next_week_item)
                logger.info(f"Updated poolOpen value for week {week_number} to: {newPoolOpenValue}")
                fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Updated poolOpen value for week {week_number} to: {newPoolOpenValue}", "INFO")
            except ClientError as error:
                logger.error(f"Error updating poolOpen value for week {week_number}: {error}")
                fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Error updating poolOpen value for week {week_number}: {error}", "ERROR")
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': 'Database error',
                        'details': str(error)})
                }

        ##
        # After updating the pool status, retrieve the updated item to return in the response
        ##
        week=getCurrentWeek()
        response = table.get_item(Key={'Week': week})

        if 'Item' in response:
            updated_pool_open = response['Item'].get('poolOpen')
            logger.info(f"Returning updated poolOpen value for week {week}: {updated_pool_open}")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'week': week,
                    'poolOpen': updated_pool_open,
                    'resultsCalculated': response['Item'].get('resultsCalculated')
                })
            }
        else:
            logger.error(f"Configuration for week {week} not found after update")
            fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Configuration for week {week} not found after update", "ERROR")
            return {
                'statusCode': 404,
                'body': json.dumps({
                    'error': f'Configuration for week {week} not found',
                    'week': week,
                    'poolOpen': False
                })
            }

    except ClientError as error:
        logger.error(f"DynamoDB Error: {error}")
        fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"DynamoDB Error: {error}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Database error',
                'details': str(error)
            })
        }
    except Exception as error:
        logger.error(f"Unexpected error: {error}")
        fbpLog("fbpadmin@my-fbp.com", "SetPoolStatus", f"Unexpected error: {error}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error'
            })
        }


@app.post("/setPoolStatusOpen")
def setPoolStatusOpen():
    logger.info("Setting pool status to open")
    logger.info(f"Request body: {app.current_event.json_body}")
    create_next_week=app.current_event.json_body.get("create_next_week", True)
    pool_open = app.current_event.json_body.get("pool_open", True)
    return _set_pool_status(create_next_week=create_next_week, poolAction=pool_open, forced_pool_open=True)


@app.get("/setPoolStatusClosed")
def setPoolStatusClosed():
    return _set_pool_status(create_next_week=False, poolAction="setPoolStatusClosed", forced_pool_open=False)


def lambda_handler(event, context):
    return app.resolve(event, context)
