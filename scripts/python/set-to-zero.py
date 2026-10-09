import boto3
from decimal import Decimal

TABLE_NAME = '2026-FBP-Users'
REGION     = 'us-east-1'

dynamodb = boto3.resource('dynamodb', region_name=REGION)
table    = dynamodb.Table(TABLE_NAME)

# 1. Scan all users (paginated)
items = []
response = table.scan(ProjectionExpression='email')
items.extend(response['Items'])
while 'LastEvaluatedKey' in response:
    response = table.scan(
        ProjectionExpression='email',
        ExclusiveStartKey=response['LastEvaluatedKey']
    )
    items.extend(response['Items'])

print(f"Users to update: {len(items)}")

success_count = 0
errors        = []

for item in items:
    email = item['email']
    try:
        table.update_item(
            Key={'email': email},
            UpdateExpression='SET totalCorrectPicks = :c, totalIncorrectPicks = :i, totalWins = :w',
            ExpressionAttributeValues={
                ':c': Decimal('0'),
                ':i': Decimal('0'),
                ':w': Decimal('0')
            }
        )
        print(f"  OK: {email}")
        success_count += 1
    except Exception as e:
        print(f"  ERROR: {email} — {e}")
        errors.append({'email': email, 'error': str(e)})

print(f"\n--- Update Summary ---")
print(f"  Updated : {success_count}")
print(f"  Errors  : {len(errors)}")
