import json
from decimal import Decimal
import os
from typing import Any, List, Dict
import logging
import csv
import io
import boto3
from botocore.exceptions import ClientError
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek
##
# Import json data from s3 bucket and update 2025-Schedule dynamoDb table
##


logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing ImportSpreads Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

def importSpreadsAndFinalScores(event, context):
    # return app.resolve(event, context)
    FBP_SCHEDULE_TABLE = os.environ.get('FBPSchedule2025TableName', 'FBP-Schedule-2025')
    logger.info(f"Using DynamoDB table: {FBP_SCHEDULE_TABLE}")  # Log the table name being used
    fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", "Lambda function initialized", "INFO")
    s3 = boto3.client('s3')
    bucket_name = os.environ.get('S3BucketName', 'my-fbp.com')
    logger.info(f"Using S3 bucket: {bucket_name}")  # Log the bucket name being used
    week=getCurrentWeek()
    if week is None:
        logger.error("Failed to determine current week. Aborting import process.")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", "Failed to determine current week. Aborting import process.", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Failed to determine current week'})
        }
    csvKey = f"schedule/2025-Schedule/week{int(week)}-schedule.csv"
    logger.info(f"Constructed S3 key for CSV file: {csvKey}")  # Log the constructed S3 key
    try:
        response = s3.get_object(Bucket=bucket_name, Key=csvKey)

        dynamodb = boto3.resource('dynamodb')
        FBP_SCHEDULE_TABLE = os.environ.get('FBPSchedule2025TableName', '2025-Schedule')
        table = dynamodb.Table(FBP_SCHEDULE_TABLE)

        logger.info(f"Processing file: {csvKey} from bucket: {bucket_name}")  # Log the file being processed
        logger.info("Starting to process spreads data and update DynamoDB")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Starting to process spreads data from {csvKey} and update DynamoDB", "INFO")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Retrieved spreads data from {csvKey}", "INFO")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Starting to process spreads data from {csvKey} and update DynamoDB", "INFO")


        content = response['Body'].read().decode('utf-8')
        reader = csv.DictReader(io.StringIO(content))
        spreads_data = list(reader)

        logger.info(f"Retrieved {len(spreads_data)} objects from bucket: {bucket_name}")
        week = getCurrentWeek()
        for spread in spreads_data:
            game_id = spread.pop('GameId', None)  # save before popping
            spread['Week'] = week
            spread['Spread'] = Decimal(str(spread['Spread']))
            ##
            # update the Underdog field.  You MUST update the csv file first.
            ##
            underdog=spread['Underdog']  ## Can be either "H" or "A"
            ##
            # Update the HomeScore and AwayScore
            ##
            spread['HomeScore']=Decimal(str(spread['HomeScore']))
            spread['AwayScore']=Decimal(str(spread['AwayScore']))
            try:     
                table.update_item(
                    Key={
                        'Week': week,
                        'GameId': game_id
                    },
                    UpdateExpression="SET #spread = :spread, #underdog = :underdog, #homeScore = :homeScore, #awayScore = :awayScore",
                    ExpressionAttributeNames={"#spread": "Spread", "#underdog": "Underdog", "#homeScore": "HomeScore", "#awayScore": "AwayScore"},
                    ExpressionAttributeValues={":spread": spread['Spread'], ":underdog": underdog, ":homeScore": spread['HomeScore'], ":awayScore": spread['AwayScore']}
                )
            except ClientError as e:
                error_msg = e.response.get('Error', {}).get('Message', str(e))
                logger.exception(f"Failed to insert spread data into DynamoDB for game: {spread['homeTeam']} vs {spread['awayTeam']}. Error: {error_msg}")
                fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Failed to insert spread data into DynamoDB for game: {spread['homeTeam']} vs {spread['awayTeam']}. Error: {error_msg}", "ERROR")
            except Exception as e:
                logger.exception(f"Unexpected error while processing spread data for game: {spread['homeTeam']} vs {spread['awayTeam']}. Error: {str(e)}")
                fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Unexpected error while processing spread data for game: {spread['homeTeam']} vs {spread['awayTeam']}. Error: {str(e)}", "ERROR")
        logger.info(f"Finished processing spreads data from {csvKey} and updating DynamoDB")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Finished processing spreads data from {csvKey} and updating DynamoDB", "INFO")
        ##
        # Move the processed file to an archive folder in S3
        ##
        archive_key = f"schedule/2025-Schedule/archive/week{week}-schedule.csv"
        try:
            s3.copy_object(Bucket=bucket_name, CopySource={'Bucket': bucket_name, 'Key': csvKey}, Key=archive_key)
            s3.delete_object(Bucket=bucket_name, Key=csvKey)
            logger.info(f"Moved processed file from {csvKey} to {archive_key} in bucket: {bucket_name}")
            fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", 
                   f"Moved processed file from {csvKey} to {archive_key} in bucket: {bucket_name}", "INFO")
        except ClientError as e:
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.exception(f"Failed to move processed file from {csvKey} to {archive_key} in bucket: {bucket_name}. Error: {error_msg}")
            fbpLog("fbpadmin@my-fbp.com", "ImportSpreads",
                   f"Failed to move processed file from {csvKey} to {archive_key} in bucket: {bucket_name}. Error: {error_msg}", "ERROR")
            return {
                'statusCode': 202,
                'body': json.dumps({
                    'error': f'Spreads and Final Scores loaded, but failed to move processed file from {csvKey} to {archive_key} in bucket: {bucket_name}'
                })
            }
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Successfully imported spreads data from {csvKey} and updated DynamoDB',
                'recordsProcessed': len(spreads_data)
            })
        }
    except ClientError as e:
        logger.exception(f"Failed to list objects in S3 bucket: {bucket_name}. Error: {e.response['Error']['Message']}")
        fbpLog("fbpadmin@my-fbp.com", "ImportSpreads", f"Failed to list objects in S3 bucket: {bucket_name}. Error: {e.response['Error']['Message']}", "ERROR")
    return {
        'statusCode': 500,
        'body': json.dumps({
            'error': f'Failed to import spreads data from S3 bucket: {bucket_name}'
        })
    }
