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
table=dynamodb.Table(os.environ.get('FBPBlockChainTableName', '2026-FBPBlockchain'))
logger.info("Blockchain table initialized: %s", table.table_name)
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
        
        # Validate at least one search parameter
        if not email and not event_type:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'error': 'At least one search parameter (email or event) is required',
                    'usage': 'Provide "email" and/or "event" in queryStringParameters or body'
                })
            }
        
        results = []
        source_count = {}
        
        # Update these GSI names to match your actual index names
        EMAIL_INDEX_NAME = os.environ.get('FBPBlockChainEmailIndexName', 'email-index')
        EVENT_INDEX_NAME = os.environ.get('FBPBlockChainEventIndexName', 'event-index')
        WEEK_INDEX_NAME = os.environ.get('FBPBlockChainWeekIndexName', 'week-index')
        
        # Query by email using GSI (fast, indexed lookup)
        if email:
            try:
                response = table.query(
                    IndexName=EMAIL_INDEX_NAME,
                    KeyConditionExpression='#pk = :pk_val',
                    ExpressionAttributeNames={'#pk': 'email'},  # Adjust if your attribute name differs
                    ExpressionAttributeValues={
                        ':pk_val': email
                    }
                )
                
                items = response.get('Items', [])
                results.extend(items)
                source_count['email_query'] = len(items)
                
                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = table.query(
                        IndexName=EMAIL_INDEX_NAME,
                        KeyConditionExpression='#pk = :pk_val',
                        ExpressionAttributeNames={'#pk': 'email'},
                        ExpressionAttributeValues={
                            ':pk_val': email
                        },
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    items = response.get('Items', [])
                    results.extend(items)
                    source_count['email_query'] += len(items)
                    
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'ResourceNotFoundException':
                    return {
                        'statusCode': 500,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({
                            'error': f'GSI "{EMAIL_INDEX_NAME}" not found. Check your index name.'
                        })
                    }
                raise
        
        # Query by event using GSI (fast, indexed lookup)
        if event_type:
            try:
                response = table.query(
                    IndexName=EVENT_INDEX_NAME,
                    KeyConditionExpression='#pk = :pk_val',
                    ExpressionAttributeNames={'#pk': 'event'},  # Adjust if your attribute name differs
                    ExpressionAttributeValues={
                        ':pk_val': event_type
                    }
                )
                
                items = response.get('Items', [])
                results.extend(items)
                source_count['event_query'] = len(items)
                
                # Handle pagination
                while 'LastEvaluatedKey' in response:
                    response = table.query(
                        IndexName=EVENT_INDEX_NAME,
                        KeyConditionExpression='#pk = :pk_val',
                        ExpressionAttributeNames={'#pk': 'event'},
                        ExpressionAttributeValues={
                            ':pk_val': event_type
                        },
                        ExclusiveStartKey=response['LastEvaluatedKey']
                    )
                    items = response.get('Items', [])
                    results.extend(items)
                    source_count['event_query'] += len(items)
                    
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                if error_code == 'ResourceNotFoundException':
                    return {
                        'statusCode': 500,
                        'headers': {'Content-Type': 'application/json'},
                        'body': json.dumps({
                            'error': f'GSI "{EVENT_INDEX_NAME}" not found. Check your index name.'
                        })
                    }
                raise
        
        # Deduplicate if both queries returned overlapping records
        seen_ids = set()
        deduplicated_results = []
        for item in results:
            # Assuming blockchain has a unique identifier (adjust if your PK differs)
            record_id = item.get('pk') or item.get('id') or str(item)
            if record_id not in seen_ids:
                seen_ids.add(record_id)
                deduplicated_results.append(item)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Cache-Control': 'no-store'  # Blockchain data shouldn't be cached
            },
            'body': json.dumps({
                'count': len(deduplicated_results),
                'queries_run': source_count,
                'results': deduplicated_results
            }, default=str)  # Handle datetime/decimal serialization
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': f'Internal error: {str(e)}',
                'traceback': os.getenv('LAMBDA_DEBUG', '').lower() == 'true' and str(type(e).__name__) or None
            }, default=str)
        }


# Local testing helper
# if __name__ == '__main__':
#     test_cases = [
#         {
#             'description': 'Search by email only',
#             'event': {
#                 'queryStringParameters': {'email': 'chuckschwing@proton.me'}
#             }
#         },
#         {
#             'description': 'Search by event only',
#             'event': {
#                 'queryStringParameters': {'action': 'SaveFBPPicks'}
#             }
#         },
#         {
#             'description': 'Search by both email and event',
#             'event': {
#                 'queryStringParameters': {
#                     'email': 'chuckschwing@proton.me',
#                     'action': 'SaveFBPPicks'
#                 }
#             }
#         },
#         {
#             'description': 'Invalid - no params',
#             'event': {'queryStringParameters': {}}
#         }
#     ]
    
#     for test in test_cases:
#         print(f"\n{'='*50}")
#         print(f"Test: {test['description']}")
#         print(f"{'='*50}")
#         result = blockchainSearch(test['event'], None)
#         print(json.dumps(result, indent=2))
        
def lambda_handler(event, context):
    return app.resolve(event, context)