from calendar import c
import json
import os
from typing import Any
import boto3
import logging
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib import getCurrentWeek


'''
This function calculates the partial weekly results for each game based on the actual game results for the week.
It queries the FBP-Schedule table for the current week and updates the Winner field for each
game based on the HomeScore, AwayScore, Spread, and Underdog fields.

The only work this function does it to calculate the NFL game results based on spread.

'''
logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing CalcPartialResultsPython Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
logger.info(f"Using DynamoDB table: {USERS_TABLE_NAME}")  # Log the table name being used
fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", "Lambda function initialized", "INFO")

cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

@app.get("/calcPartialResults")
def calcPartialResults():
    fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", "Calculating partial results", "INFO")
   
    FBP_SCHEDULE_TABLE_NAME = os.environ.get('FBPScheduleTableName', 'FBP-Schedule')
    logger.info(f"Using FBP Schedule DynamoDB table: {FBP_SCHEDULE_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME) 

    FBP_CONFIG_TABLE_NAME = os.environ.get('FBPConfigTableName', 'FBP-Config')
    logger.info(f"Using FBP Config DynamoDB table: {FBP_CONFIG_TABLE_NAME}")
    config_table = dynamodb.Table(FBP_CONFIG_TABLE_NAME)

    week=getCurrentWeek.getCurrentWeek()
    if week is None:
        logger.error("Could not determine current week")
        fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", "Could not determine current week", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Could not determine current week'}),
        }

    logger.info(f"Calculating partial weekly results for week: {week}")
    try:
        response = table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('Week').eq(week)
        )
        games = response.get('Items', [])

        if not games:
            logger.error(f"No games found for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", f"No games found for week {week}", "ERROR")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'No games found for week {week}'}),
            }
        else:
            logger.info(f"Retrieved {len(games)} games for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", f"Retrieved {len(games)} games for week {week}", "INFO")
            for game in games:
                row=calculatePartialWeeklyResults(game)
                table.update_item(
                    Key={'Week': row['Week'], 'GameId': row['GameId']},
                    UpdateExpression="SET #winner = :w",
                    ExpressionAttributeNames={'#winner': 'Winner'},
                    ExpressionAttributeValues={':w': row['Winner']}
                )
    except ClientError as e:
        logger.exception(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", f"DynamoDB Error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'DynamoDB Error'}),
        }
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "CalcPartialResultsPython", f"Unexpected error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Unexpected error'}),
        }
    return {
        'statusCode': 200,
        'body': json.dumps({'message': f'Weekly game results calculated for week {week}'}),
    }


def calculatePartialWeeklyResults(game):
    homeScore = game.get('HomeScore', 0)
    awayScore = game.get('AwayScore', 0)
    ##
    # if the homeScore and the awayScore are both 0, skip the calculation
    if homeScore == 0 and awayScore == 0:
        return game
    underDog = game.get('Underdog', 'Unknown')
    homeTeam: Any =  game.get('Home', 'Unknown')
    awayTeam: Any =  game.get('Away', 'Unknown')
    spread: Any  = game.get('Spread', 0)
    HorA: Any

    if underDog == 'H':
        homeScore += spread
    elif underDog == 'A':
        awayScore += spread
    if homeScore > awayScore:
        HorA = 'H'
    elif awayScore > homeScore:
        HorA = 'A'

        
    game['Winner'] = HorA
        
    return game

def lambda_handler(event, context):
    return app.resolve(event, context)  