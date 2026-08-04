import boto3
from boto3.dynamodb.conditions import Key
from decimal import Decimal

def query_examples():
    """
    Examples of how to query the new FBP-Results-2025 table
    """
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('FBP-Results-2025')
    
    # 1. Get all results for a specific user
    def get_user_all_weeks(email):
        response = table.query(
            KeyConditionExpression=Key('email').eq(email)
        )
        return response['Items']
    
    # 2. Get specific week result for a user
    def get_user_specific_week(email, week_num):
        response = table.query(
            KeyConditionExpression=Key('email').eq(email) & Key('week').eq(Decimal(str(week_num)))
        )
        return response['Items']
    
    # 3. Get all results for a specific week (using GSI)
    def get_week_all_users(week_num):
        response = table.query(
            IndexName='WeekIndex',
            KeyConditionExpression=Key('week').eq(Decimal(str(week_num)))
        )
        return response['Items']
    
    # 4. Get range of weeks for a user
    def get_user_week_range(email, start_week, end_week):
        response = table.query(
            KeyConditionExpression=Key('email').eq(email) & 
                                 Key('week').between(Decimal(str(start_week)), Decimal(str(end_week)))
        )
        return response['Items']
    
    # Example usage:
    print("=== Query Examples ===")
    
    # Get all weeks for a user
    user_results = get_user_all_weeks('user@example.com')
    print(f"User has {len(user_results)} week results")
    
    # Get all users for week 15
    week_results = get_week_all_users(15)
    print(f"Week 15 has {len(week_results)} participants")
    
    # Get user's results for weeks 10-15
    range_results = get_user_week_range('user@example.com', 10, 15)
    print(f"User has {len(range_results)} results in weeks 10-15")

# Run examples
query_examples()
