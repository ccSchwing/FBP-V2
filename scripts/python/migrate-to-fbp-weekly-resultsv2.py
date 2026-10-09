import boto3
from botocore.exceptions import ClientError

SOURCE_TABLE = '2026-FBP-Weekly-Results'
DEST_TABLE   = '2026-FBP-Weekly-Results-v2'
WEEK_ENDING  = '2026-10-05'
REGION       = 'us-east-1'

dynamodb = boto3.client('dynamodb', region_name=REGION)

# 1. Scan all items from the source table
paginator = dynamodb.get_paginator('scan')
items = []
for page in paginator.paginate(TableName=SOURCE_TABLE):
    items.extend(page['Items'])

print(f"Items to migrate: {len(items)}")

success_count = 0
skip_count    = 0
errors        = []

for item in items:
    email = item.get('email', {}).get('S', '')
    if not email:
        print(f"  SKIP: item missing email")
        skip_count += 1
        continue

    # Build the new item, carrying all existing attributes forward
    new_item = dict(item)

    # Add the new sort key
    new_item['weekEnding'] = {'S': WEEK_ENDING}

    # Copy lowercase 'week' -> 'Week' for the GSI if not already present
    if 'Week' not in new_item and 'week' in new_item:
        new_item['Week'] = new_item['week']

    try:
        dynamodb.put_item(
            TableName=DEST_TABLE,
            Item=new_item,
            # Safety: don't overwrite if the item already exists
            ConditionExpression='attribute_not_exists(email) AND attribute_not_exists(weekEnding)'
        )
        print(f"  OK: {email}")
        success_count += 1
    except ClientError as e:
        if e.response.get('Error', {}).get('Code') == 'ConditionalCheckFailedException':
            print(f"  SKIP (already exists): {email}")
            skip_count += 1
        else:
            print(f"  ERROR: {email} — {e}")
            errors.append({'email': email, 'error': str(e)})

print(f"\n--- Migration Summary ---")
print(f"  Migrated : {success_count}")
print(f"  Skipped  : {skip_count}")
print(f"  Errors   : {len(errors)}")
