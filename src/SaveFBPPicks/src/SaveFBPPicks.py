from calendar import c
import decimal
import json
from math import log
import random
from decimal import Decimal
import os
import re
from typing import Any, Dict, cast
import boto3
import logging
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Attr, Key
from aws_lambda_powertools import Tracer
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
from fbplib.decimalDefault import decimal_default
from fbplib.fbpLog import fbpLog
from fbplib.getCurrentWeek import getCurrentWeek


# Helper function to convert Decimal objects to int or float when serializing to JSON.
def correct_picks_value(item: Dict[str, Any]) -> int:
    v = item.get('correctPicks')
    if isinstance(v, dict) and 'N' in v:         # raw Dynamo JSON {"N":"7"}
        return int(v['N'])
    if isinstance(v, Decimal):                    # boto3 returns Decimal
        return int(v)
    try:
        return int(v)                             # already int/str fallback
    except Exception:
        return 0

'''
This function will update user picks to the FBP-Picks DynamoDB table 
for the given email address in the event.
'''
logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing SaveFBPPicksPython Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)
tracer = Tracer()


cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

pattern = re.compile(r'^[HA]*$')
def isValidPickString(s: str) -> bool:
    if s == "" or s is None:
        return False
    return bool(pattern.match(s))

@tracer.capture_method
@app.post("/saveFBPPicks")
def saveFBPPicks():
    fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", "Saving FBP picks", "INFO")
    FBP_PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', 'FBP-Picks')
    logger.info(f"Using FBP Picks DynamoDB table: {FBP_PICKS_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table(FBP_PICKS_TABLE_NAME)

    # Initialize the Users Table
    FBP_USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
    usersTable = boto3.resource('dynamodb').Table(FBP_USERS_TABLE_NAME)

    week=getCurrentWeek()
    if week is None:
        fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", "Could not determine current week", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Could not determine current week'}),
        }
    logger.info(f"Saving picks for week: {week}")
    try:
        body = app.current_event.json_body
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object")
        logger.info(f"Parsed JSON body: {body}")
        email = body.get('email')
        picks = body.get('picks')
        tieBreaker = body.get('tieBreaker')
        ## 
        # If the user left the tieBreaker blank, it gets here as ''
        # This won't do.  Get the defaultTieBreaker from the Users Table and use
        # that if it's set.  If it's not set, set it to a random number between 21 and 63
        if isinstance(tieBreaker, str) and tieBreaker == '':
            # Get the defaultTieBreaker from the Users Table
            usersData=usersTable.query(
                    KeyConditionExpression=Key('email').eq(email)
                )
            user = usersData.get('Items', [{}])[0]
            defaultTieBreaker = user.get('defaultTieBreaker')
            if defaultTieBreaker is not None:
                tieBreaker = int(defaultTieBreaker)
            else:
                tieBreaker = random.randint(21, 63)

        logger.info(f"Extracted email from API Gateway event: {email}")
        table.update_item(
            Key={'email': email}, 
            UpdateExpression="SET #picks = :p, #tieBreaker = :t, #week = :w, #picksMadeBy = :pmb",
            ExpressionAttributeNames={'#picks': 'picks', '#tieBreaker': 'tieBreaker', '#week': 'week', '#picksMadeBy': 'picksMadeBy'},
            ExpressionAttributeValues={':p': picks, ':t': tieBreaker, ':w': week, ':pmb': 'user'}
        )

        logger.info(f"Successfully saved picks: {picks} and tieBreaker: {tieBreaker} for email: {email} and week: {week}")
        fbpLog(email, "SaveFBPPicksPython", f"Successfully saved picks: {picks} and tieBreaker: {tieBreaker} for week {week}", "INFO")
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", f"DynamoDB Error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'DynamoDB Error'}),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", f"Unexpected error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Unexpected error'}),
        }
    return {
        'statusCode': 200,
        'body': json.dumps({'message': f'Successfully saved picks: {picks} and tieBreaker: {tieBreaker} for week {week}'}),
    }

@app.post("/validateAndFixFBPPicks")
@tracer.capture_method
def validateAndFixFBPPicks():
    fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", "Validating and fixing FBP picks", "INFO")
    FBP_USERS_TABLE_NAME = os.environ.get('FBPUsersTableName', 'FBP-Users')
    FBP_PICKS_TABLE_NAME = os.environ.get('FBPPicksTableName', 'FBP-Picks')
    tracer.put_annotation(key="operation", value="validateAndFixFBPPicks")
    tracer.put_annotation(key="picks_table", value=FBP_PICKS_TABLE_NAME)
    tracer.put_annotation(key="users_table", value=FBP_USERS_TABLE_NAME)
    logger.info(f"Using FBP Picks DynamoDB table: {FBP_PICKS_TABLE_NAME}")
    dynamodb = boto3.resource('dynamodb')
    picksTable = dynamodb.Table(FBP_PICKS_TABLE_NAME)
    usersTable = dynamodb.Table(FBP_USERS_TABLE_NAME)

    week=getCurrentWeek()
    if week is None:
        fbpLog("fbpadmin@my-fbp.com", "SaveFBPPicksPython", "Could not determine current week", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Could not determine current week'}),
        }
    tracer.put_annotation(key="week", value=str(week))
    logger.info(f"Validating and fixing picks for week: {week}")
    FBP_SCHEDULE_TABLE_NAME = os.environ.get('FBPScheduleTableName', '2025-Schedule')
    # need to query the schedule table for the week so that I can get the number
    # of games for that week and use it as a limit for the picks string.
    scheduleTable = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME)
    response = scheduleTable.scan(
            FilterExpression=Attr('Week').eq(week)
    )
    schedule = response.get('Items', [])
    if not schedule:
        logger.error(f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table for week {week}")
        fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table for week {week}", "ERROR")
        return Response(
            status_code=500,
            body=json.dumps({'error': 'No schedule items found'})
        )
    numberOfGames = len(schedule)
    try:
        # I think you need to get all of the email addrs and loop thru them.
        # table scan seems best.
        # keep the results in a variable the loop thru it.
        noPicks = False
        noTieBreaker = False

        # Now we can get the user and find out what algorithm they are using
        # This will capture the case where the user did not make any picks,
        # or the made SOME picks.  In the second case, the missing pick is
        # shown as a ? in the picks string.  We will replace the ? by applyin the alrorigthm
        # for the user.
        # if the user is using the default algorithm, or we will replace all picks with the default pick for that week if they are using the "pick the winner" algorithm
        #
        # for loop here to loop thru all email addrs.
        email=""
        picks=""
        userPicks=""                    ## Use this to store the original picks from the user so that we can
                                        ## show know what we changed.  This is only saved when we actually fix the picks.
        tieBreaker=""
        algorithm=""
        displayName=""
        users=usersTable.scan()
        picksFixed = False              ## Use this to set the picksMadeBy attribute in
                                        ## the Picks table to either User or System depending on whether we
                                        # had to fix the picks or not.  This will allow us to track how many users made picks
                                        # and how many had their picks fixed by the system.  This will be used for reporting
                                        # and user feedback purposes.
                                        ##
        # Set Winner field to false for all users
        ##
        for user in users.get('Items', []):
            email = user['email']
            picksResponse = picksTable.query(
                KeyConditionExpression=Key('email').eq(email),
                FilterExpression=Attr('week').eq(week-1)  ## Previous week!
            )
            if 'Items' in picksResponse and len(picksResponse['Items']) > 0:
                picksItem = picksResponse['Items'][0]
                picksItem['Winner'] = False
                picksTable.put_item(Item=picksItem)
            ##
            # Update the user record in FBP-Picks for this email.
            ##
            else:
                user['Winner'] = False
                usersTable.put_item(Item=user)
            
        logger.info(f"Resetting winner field for all users for week: {week}")
        fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Resetting winner field for all users for week: {week}", level="INFO")
        ## End of loop to reset winner field for all users for the previous week.
        # We do this at the beginning of the validateAndFixFBPPicks function because we want to make sure that
        # the winner field is reset before we start validating and fixing picks for the current week.
        ##
        for user in users.get('Items', []):
            displayName = user.get('displayName')
            email = user['email']
            logger.info(f"Validating and fixing picks for email: {email}")
            ##
            # You need to check for the current week as well.
            ##
            pickResponse = picksTable.query(
                KeyConditionExpression=Key('email').eq(email),
                FilterExpression=Attr('week').eq(week)
            )
            if 'Items' not in pickResponse or len(pickResponse['Items']) == 0:
                noPicks = True
                # We need to get the default tieBreaker.
                usersData=usersTable.query(
                    KeyConditionExpression=Key('email').eq(email)
                )
                defaultTieBreaker = usersData['Items'][0].get('defaultTieBreaker')
                if defaultTieBreaker is None:
                    logger.warning(f"No default tieBreaker found for email: {email}, setting to random number between 21 and 63")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"No default tieBreaker found for email: {email}, setting to random number between 21 and 63", level="WARNING")
                    defaultTieBreaker = random.randint(a=21, b=63)
                # convert defaultTieBreaker to a int
                defaultTieBreaker = decimal.Decimal(defaultTieBreaker)
                if defaultTieBreaker is not None:
                    decimalTieBreaker = defaultTieBreaker
                    logger.info(f"Setting tieBreaker for email: {email}, to {decimalTieBreaker}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Setting tieBreaker for email: {email}, to {decimalTieBreaker}", level="INFO")
                else:               ## Set to a random number if there is no defaultTieBreaker for the user.
                    decimalTieBreaker = random.randint(a=21, b=63)
                    logger.info(f"No default tieBreaker found for email: {email}, setting to random number: {decimalTieBreaker}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"No default tieBreaker found for email: {email}, setting to random number: {decimalTieBreaker}", level="INFO")
            else:
                picksItem = pickResponse['Items'][0]
                picks = picksItem.get('picks')
                userPicks = picks
                if picks == '':
                    noPicks=True
                decimalTieBreaker = picksItem.get('tieBreaker')
            ##
            # Check if the tieBreaker is null or missing.
            # If so, we need to set it to the defaultTieBreaker
            # for the user or a random number if there is no defaultTieBreaker. 
            ##
            if decimalTieBreaker is None or decimalTieBreaker == '':
                logger.warning(f"tieBreaker is missing for email: {email}, will attempt to set it using defaultTieBreaker")
                fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"tieBreaker is missing for email: {email}, will attempt to set it using defaultTieBreaker", level="WARNING")
                decimalTieBreaker = 0
                usersData=usersTable.query(
                    KeyConditionExpression=Key('email').eq(email)
                )
                defaultTieBreaker = usersData['Items'][0].get('defaultTieBreaker')
                if defaultTieBreaker is not None:
                    decimalTieBreaker = defaultTieBreaker
                    logger.info(f"Setting tieBreaker found for email: {email}, to {decimalTieBreaker}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Setting tieBreaker found for email: {email}, to {decimalTieBreaker}", level="INFO")
                else:               ## Set to a random number if there is no defaultTieBreaker for the user.
                    decimalTieBreaker = random.randint(a=21, b=63)
                    logger.info(f"No default tieBreaker found for email: {email}, setting to random number: {decimalTieBreaker}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"No default tieBreaker found for email: {email}, setting to random number: {decimalTieBreaker}", level="INFO")
            if decimalTieBreaker is not None:
                tieBreaker = int(decimalTieBreaker)
            # Handle the case where there are no picks.
            if picks is None:
                noPicks = True
                logger.warning(f"No picks found for email: {email}, setting noPicks flag to True")
                fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"No picks found for email: {email}, setting noPicks flag to True", level="WARNING")
            algorithm = user.get('defaultAlgorithm')
            match algorithm:
                case "home":
                    if noPicks:
                        picks = "H" * numberOfGames
                        picksFixed = True
                    else:
                        # Replace all ? with H
                        # if picks contains ? set picksFixed to true 
                        # so that we can update the picksMadeBy attribute in the Picks table to System for this user.
                        if '?' in str(picks):
                            picksFixed = True
                        picks = str(picks).replace("?", "H")
                case "away":
                    picksFixed = False
                    if noPicks:
                        picks = "A" * numberOfGames
                        picksFixed = True
                    else:
                        # Replace all ? with A
                        if '?' in str(picks):
                            picksFixed = True
                        picks = str(picks).replace("?", "A")
                case "random":
                    picksFixed = False
                    defaultPicks = ""
                    if noPicks:
                        for _ in range(numberOfGames):
                            rNumber = random.uniform(0, 1)
                            if rNumber > 0.5:
                                defaultPicks = defaultPicks + "H"
                            else:
                                defaultPicks = defaultPicks + "A"
                        picks = "".join(defaultPicks)
                        picksFixed = True
                    else:
                        picksFixed = False
                        # Replace all ? with a random pick
                        for i, c in enumerate(str(picks)):
                            if c == "?":
                                rNumber = random.uniform(0, 1)
                                defaultPicks = defaultPicks + (rNumber > 0.5 and "H" or "A")
                                picksFixed = True
                            else:
                                defaultPicks = defaultPicks + c
                        picks = defaultPicks
                        logger.info(f"Replaced ? with random picks: {picks}")
                        fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Replaced ? with random picks: {picks}", level="INFO")
                # For favorites and underdogs we need the schedule from 202X season to determine 
                # which team is the favorite and which is the underdog.
                # We will get the schedule from the DynamoDB table and then apply the
                # algorithm to replace the ? with the correct pick.
                case "favorites":
                    scheduleTable = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME)
                    # Underdog is defined in the DB as either H or A.
                    # Favorite is NOT defined, so scan for it and invert it to get the favorite.
                    response = scheduleTable.scan(
                    FilterExpression=Attr('Week').eq(week)
                    )
                    schedule = response.get('Items', [])
                    if not schedule: 
                        logger.error(f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table")
                        fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table", "ERROR")
                        return Response(
                            status_code=500,
                            body=json.dumps({'error': 'No schedule items found'})
                        )
                    if noPicks:
                        # For each game in the schedule, determine the favorite and set the pick
                        defaultPicks = "" 
                        for game in schedule:
                            if game.get('Underdog') == "H":
                                defaultPicks = defaultPicks + "A"
                            elif game.get('Underdog') == "A":
                                defaultPicks = defaultPicks + "H"
                        picks = defaultPicks
                        picksFixed = True
                        logger.info(f"Set picks to favorites: {picks}")
                        fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"Set picks to favorites: {picks}", "INFO") 
                    else:
                        defaultPicks = ""
                        picksFixed = False
                        # Replace all ? with the favorite
                        for i, c in enumerate(str(picks)):
                            if c == "?":
                                picksFixed = True
                                # Find the game in the schedule
                                for game in schedule:
                                    if game.get('Underdog') == "H":
                                        defaultPicks = defaultPicks + "A"
                                        picksFixed = True
                                    elif game.get('Underdog') == "A":
                                        defaultPicks = defaultPicks + "H"
                                        picksFixed = True
                        if picksFixed:
                            picks = defaultPicks
                            logger.info(f"Replaced ? with favorites picks: {picks}")
                            fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Replaced ? with favorites picks: {picks}", level="INFO")
                case "underdogs":
                    scheduleTable = dynamodb.Table(FBP_SCHEDULE_TABLE_NAME)
                    # Underdog is defined in the DB as either H or A.
                    response = scheduleTable.scan(
                    FilterExpression=Attr('Week').eq(week)
                    )
                    schedule = response.get('Items', [])
                    if not schedule:
                        logger.error(f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table")
                        fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"No schedule items found in {FBP_SCHEDULE_TABLE_NAME} table", "ERROR")
                        return Response(
                            status_code=500,
                            body=json.dumps({'error': 'No schedule items found'})
                        )
                    if noPicks:
                        defaultPicks = ""
                        for game in schedule:
                            if game.get('Underdog') == "H":
                                defaultPicks = defaultPicks + "H"
                            elif game.get('Underdog') == "A":
                                defaultPicks = defaultPicks + "A"
                        picks = defaultPicks
                        picksFixed = True
                        logger.info(f"Set picks to underdogs: {picks}")
                        fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Set picks to underdogs: {picks}", level="INFO")
                    else:
                        defaultPicks = ""
                        picksFixed = False
                        # Replace all ? with the underdog
                        for i, c in enumerate(str(picks)):
                            if c == "?":
                                picksFixed = True
                                # Find the game in the schedule
                                for game in schedule:
                                    if game.get('Underdog') == "H":
                                        defaultPicks = defaultPicks + "H"
                                        picksFixed = True
                                    elif game.get('Underdog') == "A":
                                        defaultPicks = defaultPicks + "A"
                                        picksFixed = True
                        if picksFixed:
                            picks = defaultPicks
                            logger.info(f"Replaced ? with underdog picks: {picks}")
                            fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"Replaced ? with underdog picks: {picks}", "INFO")                
            # End of match statement to apply algorithm to replace ? with the correct pick.

            ##
            # setting this none doesn't make sense.
            ## 
            defaultTieBreaker = None
            if noPicks:

                userData=usersTable.query(
                    KeyConditionExpression=Key('email').eq(email)
                )
                defaultTieBreaker = userData['Items'][0].get('defaultTieBreaker')  # type: ignore
                if defaultTieBreaker is None:
                    defaultTieBreaker = random.randint(a=21, b=49)
                    logger.info(f"No default tieBreaker found for email: {email}, setting to random number: {defaultTieBreaker}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"No default tieBreaker found for email: {email}, setting to random number: {defaultTieBreaker}", level="INFO")
                else:
                    logger.info(f"Extracted default tieBreaker: {defaultTieBreaker} for email: {email}")
                    fbpLog(email=email, action="method: validateAndFixFBPPicks", details=f"Extracted default tieBreaker: {defaultTieBreaker} for email: {email}", level="INFO")
            if noTieBreaker:
                tieBreaker = defaultTieBreaker
            if picksFixed:
                pmb='System'
                picksTable.update_item(
                    Key={'email': email}, 
                    UpdateExpression="SET #picks = :p, #tieBreaker = :t, #week = :w, #displayName = :d, #picksMadeBy = :pmb, #userPicks = :up",
                    ExpressionAttributeNames={'#picks': 'picks', '#tieBreaker': 'tieBreaker', '#week': 'week', '#displayName': 'displayName', '#picksMadeBy': 'picksMadeBy', '#userPicks': 'userPicks'},
                    ExpressionAttributeValues={':p': picks, ':t': tieBreaker, ':w': week, ':d': displayName, ':pmb': pmb, ':up': userPicks}
            )
            else:
                pmb='User'
                userPicks = ""
                picksTable.update_item(
                    Key={'email': email}, 
                    UpdateExpression="SET #picks = :p, #tieBreaker = :t, #week = :w, #displayName = :d, #picksMadeBy = :pmb, #userPicks = :up",
                    ExpressionAttributeNames={'#picks': 'picks', '#tieBreaker': 'tieBreaker', '#week': 'week', '#displayName': 'displayName', '#picksMadeBy': 'picksMadeBy', '#userPicks': 'userPicks'},
                    ExpressionAttributeValues={':p': picks, ':t': tieBreaker, ':w': week, ':d': displayName, ':pmb': pmb, ':up': userPicks}
            )

            ##
            # You need to reset your relevant flags and variables here for the next user in the loop.
            noPicks = False
            picksFixed = False
            noTieBreaker = False
            email=""
            picks=""
            userPicks=""
            tieBreaker=""
            algorithm=""
            displayName=""
        # End of for loop to validate and fix picks for each user.  By the time we get here,
        # we should have valid picks and tieBreaker values for each user for the current week.
        logger.info(f"Successfully validated and fixed picks: {picks} and tieBreaker: {tieBreaker} for week {week}")
        fbpLog(email, "SaveFBPPicksPython", f"Successfully validated and fixed picks: {picks} and tieBreaker: {tieBreaker} for week {week}", "INFO")
    except ClientError as e:
        logger.error(f"DynamoDB Error: {e}")
        fbpLog(email="fbpadmin@my-fbp.com", action="method: validateAndFixFBPPicks", details=f"DynamoDB Error: {e}", level="ERROR")
        return{
            'statusCode': 500,
            'body': json.dumps({'error': 'DynamoDB Error'}),
        }
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        fbpLog("fbpadmin@my-fbp.com", "method: validateAndFixFBPPicks", f"Unexpected error: {e}", "ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Unexpected error'}),
        }
    return {
        'statusCode': 200,
        'body': json.dumps({'message': f'Successfully validated and fixed picks: {picks} and tieBreaker: {tieBreaker} for week {week}'}),
    }


@tracer.capture_lambda_handler
def lambda_handler(event, context):
    return app.resolve(event, context)  