import json
import os
import re
import boto3
import logging
from decimal import Decimal
from typing import List, Dict, Any
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek


'''
This function calcualates the weekly results for each user based on
their picks and the actual game results for the week.
Updates the FBP_WEEKLY_RESULTS_TABLE with the number of correct and incorrect picks for each user for the week and
whether they were the winner for the week. Also updates the FBP_USERS_TABLE with the
total correct and incorrect picks for each user for the week.
Inrements the totalwins for the winner.
'''

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing UpdatePartialResults Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)

cors_config = CORSConfig(
    allow_origin="*",
    allow_headers=[
        "Content-Type",
        "X-Amz-Date",
        "Authorization",
        "X-Api-Key",
        "X-Amz-Security-Token",
    ],
    max_age=86400,
    allow_credentials=False,
)

app = APIGatewayHttpResolver(cors=cors_config)

##
# this is called after we do the partial weekly results update
##
@app.get("/updatePartialCorrectAndIncorrectPicks")
def updatePartialCorrectAndIncorrectPicks():
    # Loop through the FBP_WEEKLY_RESULTS_TABLE and update
    # the FBP_USERS_TABLE with the total correct and incorrect
    # picks for each user for the season.
    FBP_USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', '2026-FBP-Users')
    logger.info(f"Using FBP Users DynamoDB table: {FBP_USERS_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    usersTable = dynamodb.Table(FBP_USERS_TABLE_NAME)
    FBP_WEEKLY_RESULTS_TABLE = os.environ.get('FBPWeeklyResultsTable', '2026-FBP-Weekly-Results')
    logger.info(f"Using DynamoDB table: {FBP_WEEKLY_RESULTS_TABLE}")
    resultsTable = dynamodb.Table(FBP_WEEKLY_RESULTS_TABLE)

    users=usersTable.scan().get('Items', [])
    for user in users:
        email = user.get('email')
        totalCorrectPicks = 0
        totalIncorrectPicks = 0
        response = resultsTable.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('email').eq(email)
        )
        weeklyResults = response.get('Items', [])
        for result in weeklyResults:
            totalCorrectPicks += result.get('correctpicks', 0)
            totalIncorrectPicks += result.get('incorrectpicks', 0)
        usersTable.update_item(
            Key={'email': email},
            UpdateExpression="SET totalCorrectPicks = :totalCorrectPicks, totalIncorrectPicks = :totalIncorrectPicks",
            ExpressionAttributeValues={
                ':totalCorrectPicks': totalCorrectPicks,
                ':totalIncorrectPicks': totalIncorrectPicks
            }
        )
    return Response(
        status_code=200,
        content_type="application/json",
        body=json.dumps({'message': 'Updated total correct and incorrect picks for all users'}),
    )

##
# this is the entry point for updating partial weekly results
##
@app.get("/updatePartialWeeklyResults")
def updatePartialWeeklyResults():
    FBP_WEEKLY_RESULTS_TABLE = os.environ.get('FBPWeeklyResultsTable', '2026-FBP-Weekly-Results')
    logger.info(f"Using DynamoDB table: {FBP_WEEKLY_RESULTS_TABLE}")  # Log the table name being used
    fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", "Retrieving weekly results", "INFO")
    '''
    FBP_USERS_TABLE contains the entries for each user, including their email, totalCorrectPicks, and totalIncorrectPicks,
    and whether the user was the winner for the week. This table is updated with the total correct and incorrect picks for
    the week for each user after each week.
    FBP_PICKS_TABLE contains the entries for each user's picks for each week, including
    email address week and tieBreaker.
    This table is the raw data for calculating the weekly results.
    FBP_WEEKLY_RESULTS_TABLE contains the entries for each user's results for each week, including email,
    week, correctpicks, incorrectpicks, and whether they were the winner for the week. It also
    contains the totatwins for the user for the season.
    '''
    FBP_USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', '2026-FBP-Users')
    logger.info(f"Using FBP Users DynamoDB table: {FBP_USERS_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    resultsTable = dynamodb.Table(FBP_WEEKLY_RESULTS_TABLE) 
    usersTable = dynamodb.Table(FBP_USERS_TABLE_NAME)

    FBP_PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', '2026-FBP-Picks')
    logger.info(f"Using FBP Picks DynamoDB table: {FBP_PICKS_TABLE_NAME}")
    picksTable = dynamodb.Table(FBP_PICKS_TABLE_NAME)
    logger.info(f"Using FBP Picks DynamoDB table: {FBP_PICKS_TABLE_NAME}")


    week=getCurrentWeek()
    if week is None:
        fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", "Could not determine current week", "ERROR")
        return Response (
            status_code=500,
             content_type="application/json",
             body=json.dumps({'error': 'Could not determine current week'}),
        )
    logger.info(f"Retrieving results for week: {week}")
    fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Retrieving results for week: {week}", "INFO")

    try:
        '''
        Get all picks for the week from the FBP_PICKS_TABLE and calculate the number of correct and incorrect picks for each user.
        Then update the FBP_WEEKLY_RESULTS_TABLE with the number of correct and incorrect picks for each user and
        whether they were the winner for the week. Finally, update the FBP_USERS_TABLE
        '''
        response = picksTable.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('week').eq(week)
        )
        allUserPicks  = response.get('Items', [])

        if not allUserPicks:
            logger.error(f"No picks found for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"No picks found for week {week}", "ERROR")
            return Response (
                status_code=404,
                content_type="application/json",
                body=json.dumps({'error': f'No picks found for week {week}'}),
            )
        else:
            logger.info(f"Retrieved {len(allUserPicks)} picks for week {week}")
            fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Retrieved {len(allUserPicks)} picks for week {week}", "INFO")
            '''
            Update the FBP_WEEKLY_RESULTS_TABLE with the number of correct and incorrect picks for each user,
            whether they were the winner for the week, incement the total wins for the winner,
            and update the FBP_USERS_TABLE with the total correct and incorrect picks for each user for the season.
            '''
            weeklyResults = updatePartialWeeklyUserResults(allUserPicks=allUserPicks, resultsTable=resultsTable, usersTable=usersTable, week=week)
            if weeklyResults.status_code != 200:
                logger.error("Failed to update weekly user results")
                fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", "Failed to update weekly user results", "ERROR")
                return weeklyResults
            else:
                logger.info(f"Updated weekly user results for week {week}")
                fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Updated weekly user results for week {week}", "INFO")
                return weeklyResults
    except ClientError as e:
        logger.exception(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"DynamoDB Error: {e}", "ERROR")
        return Response (
            status_code=500,
            content_type="application/json",
            body=json.dumps({'error': 'DynamoDB Error'}),
        )
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Unexpected error: {e}", "ERROR")
        return Response (
            status_code=500,
            content_type="application/json",
            body=json.dumps({'error': 'Unexpected error'}),
        )
def getResultsCalculatedValueForWeek(week: int) -> Any:
    dynamodb = boto3.resource('dynamodb')
    FBP_CONFIG_TABLE_NAME = os.environ.get('FBPConfigTableName', 'FBP-Config')
    logger.info(f"Using FBP Config DynamoDB table: {FBP_CONFIG_TABLE_NAME}")
    configTable = dynamodb.Table(FBP_CONFIG_TABLE_NAME)
    try:
        configResponse = configTable.get_item(Key={'Week': week})
        if 'Item' not in configResponse:
            logger.error(f"Configuration for week {week} not found in FBP-Config table")
            fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Configuration for week {week} not found in FBP-Config table", "ERROR")
            return Response (
                status_code=404,
                content_type="application/json",
                body=json.dumps({'error': f'Configuration for week {week} not found'}),
            )
        resultsCalculated = configResponse['Item'].get('resultsCalculated')
        if resultsCalculated is None:
            logger.error(f"resultsCalculated value not found for week {week} in FBP-Config table")
            fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"resultsCalculated value not found for week {week} in FBP-Config table", "ERROR")
            return Response (
                status_code=404,
                content_type="application/json",
                body=json.dumps({'error': f'resultsCalculated value not found for week {week}'}),
            )
        return Response (
            status_code=200,
            content_type="application/json",
            body=json.dumps({'week': week, 'resultsCalculated': resultsCalculated}),
        )
    except ClientError as e:
        logger.error(f"Error retrieving configuration for week {week} from FBP-Config table: {e}")
        fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Error retrieving configuration for week {week} from FBP-Config table: {e}", "ERROR")
        return Response (
            status_code=500,
            content_type="application/json",
            body=json.dumps({'error': f'Error retrieving configuration for week {week}'}),
        )

def updatePartialWeeklyUserResults(allUserPicks: List[Dict[str, Any]], resultsTable, usersTable, week: int) -> Response:
    dynamodb = boto3.resource('dynamodb')
    FBP_CONFIG_TABLE_NAME = os.environ.get('FBPConfigTableName', 'FBP-Config')
    logger.info(f"Using FBP Config DynamoDB table: {FBP_CONFIG_TABLE_NAME}")
    configTable = dynamodb.Table(FBP_CONFIG_TABLE_NAME)

    ##
    # Get the value of resultsCalculated for the current week from the FBP-Config table.
    # If resultsCalculated is true, then we should not run this method again for the current week.
    ##
    try:
        configResponse = configTable.get_item(Key={'Week': week})
        if 'Item' not in configResponse:
            logger.error(f"Configuration for week {week} not found in FBP-Config table")
            fbpLog("fbpadmin@my-fbp.com", "UpdateWeeklyResults", f"Configuration for week {week} not found in FBP-Config table", "ERROR")
            return Response(status_code=404, content_type="application/json", body=json.dumps({'error': f'Configuration for week {week} not found'}))

        result=getResultsCalculatedValueForWeek(week)
        if isinstance(result, Response):
            if result.status_code != 200:
                logger.error(f"Error retrieving resultsCalculated value for week {week}: {result.body}")
                fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"Error retrieving resultsCalculated value for week {week}: {result.body}", "ERROR")
                return Response(status_code=500, content_type="application/json", body=json.dumps({'error': f'Error retrieving resultsCalculated for week {week}'}))
            resultsCalculated = json.loads(result.body).get('resultsCalculated') if result.body else None
        else:
            resultsCalculated = result.get('resultsCalculated') if result else None
        if resultsCalculated:
            logger.info(f"Results for week {week} have already been calculated")
            fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"Results for week {week} have already been calculated", "INFO")
            return Response(status_code=200, content_type="application/json", body=json.dumps({'message': f'Results for week {week} have already been calculated'}))
    except ClientError as e:
        logger.error(f"Error retrieving configuration for week {week} from FBP-Config table: {e}")
        fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"Error retrieving configuration for week {week} from FBP-Config table: {e}", "ERROR")
        return Response(status_code=500, content_type="application/json", body=json.dumps({'error': f'Error retrieving configuration for week {week}'}))  
    ##
    # If we get here, it's safe to proceed.  Full weekly results are not calculated yet.
    ##

    FBP_SCHEDULE_TABLE_NAME = os.environ.get('FBPScheduleTableName', '2026-Schedule')
    logger.info(f"Using FBP Schedule DynamoDB table: {FBP_SCHEDULE_TABLE_NAME}")
    scheduleTable = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME)
    scheduleResults = scheduleTable.scan(
        FilterExpression=boto3.dynamodb.conditions.Attr('Week').eq(week)
    )
    if not scheduleResults.get('Items'):
        logger.warning(f"No schedule found for week {week}")
        fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"No schedule found for week {week}", "WARNING")
        return Response(status_code=404, content_type="application/json", body=json.dumps({'error': f'No schedule found for week {week}'}))

    scheduleItems  = scheduleResults.get('Items', [])
    scheduleItems = sorted(scheduleItems, key=lambda x: str(x['GameId']))  # Sort by GameId to ensure correct order
    ##
    # Check to see if Home Score is zero and Away Score is zero
    # If both scores are zero, the game has not been played yet.
    # skip it.
    # Need to get the index into scheduleItems for games with non-zero home and away scores.
    gameResultsDict = {}
    index = 0
    for index, game in enumerate(scheduleItems):
        if game['HomeScore'] == 0 and game['AwayScore'] == 0:
            continue
        else:
            gameResultsDict[index] = game['Winner']  # Either H or A
        ##
        # Now, let's build the gameResults dictionary with the correct order of games.
        # The gameResults dictionary will be used to compare the user's picks to the actual game results.
        ##
    
    ##
    # At this point, gameResults contains the results for all games that have been played.
    # The keys are the indices of the games in scheduleItems, and the values are the winners ('H' or 'A').

    # scheduleItems = [game for game in scheduleItems if not (game['HomeScore'] == 0 and game['AwayScore'] == 0)]
    ##
    # use full game list
    ##
    gameIndex = 0
    for game in scheduleItems:
        if game['HomeScore'] == 0 and game['AwayScore'] == 0:
            gameIndex += 1
            continue
        ## 
        # Now you've got the index into the gameResults dictionary for the current completed game.
        ##
        logger.info(f"Processing game {game['GameId']} with winner {game['Winner']} for week {week}")
        logger.info(f"Game Results so far: {gameResultsDict}")
        winnerOfGame = game['Winner']
        gameResultsDict[gameIndex] = winnerOfGame  # Either H or A 
        gameIndex += 1
    '''
    Now we have the results for each game for the week in gameResults.
    We can now calculate the number of correct and incorrect picks for each user.
    '''
    ##
    # gameResults holds the results for all completed games for the week.
    ##
    ##
    gameResultsJSON = []

    for picks in allUserPicks:
        '''
        Get the picks for the user and compare them to the game results to
        calculate the number of correct and incorrect picks for the user.
        '''
        index = 0
        userPicks= picks['picks']  # This is a list of picks for the user for the week
        userPicks=list(userPicks)  # Convert the picks to a list of picks in the correct order
        correctpicks = 0
        incorrectpicks = 0
        ##
        # get the key value from gameResultDict and get the corresponding pick from userPicks
        for gameResultsKey in gameResultsDict.keys():
            userPick = userPicks[gameResultsKey]
            if userPick == gameResultsDict[gameResultsKey]:
                correctpicks += 1
            else:
                incorrectpicks += 1
                
            
        email=picks['email']


        # use email to get displayName from FBP_USERS_TABLE
        displayName = "Unknown User"
        try:
            userResponse = usersTable.get_item(
                Key={'email': email}
            )
            displayName = userResponse.get('Item', {}).get('displayName', 'Unknown User')
        except ClientError as e:
            logger.exception(f"DynamoDB Error: {e}")
            fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", 
                   f"Failed to get displayName for {email} from DynamoDB: {e}", "ERROR")
        try:
            resultsTable.update_item(
                Key={'email': email},
                UpdateExpression="SET correctpicks = :c, incorrectpicks = :i, displayName = :d, #w = :w",
                ExpressionAttributeNames={'#w': 'week'},
                ExpressionAttributeValues={':c': Decimal(correctpicks), ':i': Decimal(incorrectpicks), ':d': displayName, ':w': Decimal(week)}
            )
        except ClientError as e:
            logger.exception(f"DynamoDB Error: {e}")
            fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"DynamoDB Error: {e}", "ERROR")
            return Response(status_code=500, content_type="application/json", body=json.dumps({'error': f'DynamoDB error saving results for {email}'}))
        logger.info(f"Updated partial weekly results for user: {email} with correct picks: {correctpicks} and incorrect picks: {incorrectpicks}")
        fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"Updated partial weekly results for user: {email} with correct picks: {correctpicks} and incorrect picks: {incorrectpicks}", "INFO")
        '''
        Create a JSON String with the user's email, correct picks, and incorrect picks for the week.
        '''

        ##
        # Skip over any system users from FBP_USERS_TABLE.
        # We only want to include real users in the results.
        ##
        try:
            userResponse = usersTable.get_item(
                Key={'email': email}
            )
            userType = userResponse.get('Item', {}).get('userType', 'unknown')
            if userType == 'user':
                # Only include real users in the results
                weeklyResult = {
                    'displayName': displayName,
                    'correctPicks': correctpicks,
                    'incorrectPicks': incorrectpicks
                }
                gameResultsJSON.append(weeklyResult)
            else:
                continue  # Skip system users 
        except ClientError as e:
            logger.exception(f"DynamoDB Error: {e}")
            fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"DynamoDB Error: {e}", "ERROR")
            continue  # Skip this user if there's an error retrieving userType

    # End of for loop for each user's picks for the week.
    # Now, call updateTotalCorrectAndIncorrectPicks to update the FBP_USERS_TABLE with the
    # total correct and incorrect picks for each user for the season.
    ##
    # Not sure I want to call the full updateTotalCorrectAndIncorrectPicks here, but for now we won't.

    # updatePartialCorrectAndIncorrectPicks()

    # now you can set the Winner field for each user in the
    # FBP_WEEKLY_RESULTS_TABLE based on the number of correct picks for the week.
    ##
    # Make sure to filter the scan for the current week and only update the winner for the current week.
    logger.info(f"Updated Partial User results for week {week}")
    fbpLog("fbpadmin@my-fbp.com", "UpdatePartialWeeklyResults", f"Updated User results for week {week}", "INFO")
    gameResultsJSON.sort(key=lambda x: x['correctPicks'], reverse=True)  # Sort the results by correct picks in descending order
    return Response(status_code=200, content_type="application/json", body=json.dumps(gameResultsJSON))

def lambda_handler(event, context):
    print("Received event:", json.dumps(event))  # Log the received event for debugging
    return app.resolve(event, context)