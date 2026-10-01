import json
import boto3
from botocore.exceptions import ClientError
from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.api_gateway import CORSConfig
import os
import logging

logging.basicConfig(format='%(levelname)s %(message)s')
logger = logging.getLogger()
logger.info("Initializing SaveFBPPicksPython Lambda function")  # Log initialization message
logger.setLevel(logging.INFO)


cors_config = CORSConfig(
    allow_origin="*",  # Or specify your domain like "https://yourdomain.com"
    allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token"],
    max_age=86400,  # Cache preflight for 24 hours
    allow_credentials=False
)

app=APIGatewayHttpResolver(cors=cors_config)

# Create DynamoDB resource (reuse outside handler)
dynamodb = boto3.resource('dynamodb')
bcTable=dynamodb.Table(os.environ.get('FBPBlockChainTableName', '2026-FBPBlockchain'))
logger.info("Blockchain table initialized: %s", bcTable.table_name)
@app.post("/blockchainSearch")
def blockchainSearch():
    """
    Lambda handler for searching the blockchain table using GSIs.
    
    Expected parameters:
    - email: query email GSI (partition key)
    - event: query event GSI (partition key)
    
    Example invocation:
    {
        "queryStringParameters": {
            "email": "user@example.com",
            "event": "transfer"
        }
    }
    """
    
    try:
        # Extract search parameters
        query_params = app.current_event.query_string_parameters or {}
        body_params = app.current_event.json_body or {}
        
        email = query_params.get('email') or body_params.get('email')
        ##
        # this should be action, not event.
        ##
        event_type = query_params.get('event') or body_params.get('event')
        week = query_params.get('week') or body_params.get('week')
        
        # Validate at least one search parameter
        if not email and not event_type and not week:
            return Response(
                status_code=400,
                content_type="application/json",
                body=json.dumps({
                    'error': 'At least one search parameter (email or event) is required',
                    'usage': 'Provide "email" and/or "event" in queryStringParameters or body'
                })
            )
        
        EMAIL_INDEX_NAME = os.environ.get('FBPBlockChainEmailIndexName', 'email-index')
        EVENT_INDEX_NAME = os.environ.get('FBPBlockChainEventIndexName', 'event-index')
        WEEK_INDEX_NAME = os.environ.get('FBPBlockChainWeekIndexName', 'week-index')

        def query_gsi(index_name, attr_name, attr_value):
            items = []
            kwargs = {
                'IndexName': index_name,
                'KeyConditionExpression': '#pk = :pk_val',
                'ExpressionAttributeNames': {'#pk': attr_name},
                'ExpressionAttributeValues': {':pk_val': attr_value}
            }
            try:
                response = bcTable.query(**kwargs)
                items.extend(response.get('Items', []))
                while 'LastEvaluatedKey' in response:
                    response = bcTable.query(**kwargs, ExclusiveStartKey=response['LastEvaluatedKey'])
                    items.extend(response.get('Items', []))
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'ResourceNotFoundException':
                    raise ValueError(f'GSI "{index_name}" not found. Check your index name.')
                raise
            return items

        # Query the first provided param, then intersect with subsequent ones
        filters = []
        if email:      filters.append(('email',  EMAIL_INDEX_NAME, 'email',  email))
        if event_type: filters.append(('event',  EVENT_INDEX_NAME, 'event',  event_type))
        if week:       filters.append(('week',   WEEK_INDEX_NAME,  'week',   week))

        # Start with results from the first GSI
        _, first_index, first_attr, first_val = filters[0]
        result_items = query_gsi(first_index, first_attr, first_val)

        # AND: keep only items that also match every remaining filter
        for _, _, attr, val in filters[1:]:
            result_items = [item for item in result_items if item.get(attr) == val]

        return Response(
            status_code=200,
            content_type="application/json",
            headers={'Cache-Control': 'no-store'},
            body=json.dumps({
                'count': len(result_items),
                'results': result_items
            }, default=str)
        )
        
    except Exception as e:
        return Response(
            status_code=500,
            content_type="application/json",
            body=json.dumps({
                'error': f'Internal error: {str(e)}',
                'traceback': os.getenv('LAMBDA_DEBUG', '').lower() == 'true' and str(type(e).__name__) or None
            }, default=str)
        )

@app.get("/getBlockchainAttributes")
def getBlockchainAttributes():
    emailList = []
    eventList = []
    weekList = []
    ##
    # I need to get a distinct list of emails, events and weeks from the blockchain table
    ##
    dynamodb = boto3.resource('dynamodb')
    bcTable = dynamodb.Table(os.environ.get('FBPBlockChainTableName', '2026-FBPBlockChain'))
    
    try:
        response = bcTable.scan()
        items = response.get('Items', [])
        for item in items:
            email = item.get('email')
            event = item.get('event')
            week = item.get('week')
            if email and email not in emailList:
                emailList.append(email)
            if event and event not in eventList:
                eventList.append(event)
            if week and week not in weekList:
                weekList.append(week)
    except ClientError as e:
        logger.error(f"Error scanning blockchain table: {e}")
    return {
        'emailList': emailList,
        'eventList': eventList,
        'weekList': weekList
    }
    
    
def lambda_handler(event, context):
    return app.resolve(event, context)