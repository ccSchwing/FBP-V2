import boto3
from decimal import Decimal
from boto3.dynamodb.conditions import Key
import time

def migrate_fbp_data(current_week_number):
    """
    Migrate data from FBP-Weekly-Results to FBP-Weekly-Results-2025
    
    Args:
        current_week_number (int): The week number for the current data (e.g., 15 for Week 15)
    """
    dynamodb = boto3.resource('dynamodb')
    
    # Source and destination tables
    source_table = dynamodb.Table('FBP-Weekly-Results')
    dest_table = dynamodb.Table('FBP-Weekly-Results-2025')
    
    try:
        # Scan all items from source table
        print("Scanning source table...")
        response = source_table.scan()
        items = response['Items']
        
        # Handle pagination if there are more items
        while 'LastEvaluatedKey' in response:
            response = source_table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response['Items'])
        
        print(f"Found {len(items)} items to migrate")
        
        # Migrate items in batches
        migrated_count = 0
        failed_items = []
        
        with dest_table.batch_writer() as batch:
            for item in items:
                try:
                    # Transform the item for the new table structure
                    new_item = {
                        'email': item['email'],  # Assuming email is the partition key in source
                        'week': Decimal(str(current_week_number)),  # Convert to Decimal for DynamoDB
                        'correctpicks': item['correctPicks'],  # Use actual value from source
                        'incorrectpicks': item['incorrectPicks'],  # Use actual value from source
                        'winner': item['Winner'],
                        'totalwins': item.get('totalwins', Decimal('0'))  # Use actual value from source
                    }
                    
                    # Write to destination table
                    batch.put_item(Item=new_item)
                    migrated_count += 1
                    
                    if migrated_count % 25 == 0:  # Progress update every 25 items
                        print(f"Migrated {migrated_count} items...")
                        
                except Exception as e:
                    print(f"Failed to migrate item {item.get('email', 'unknown')}: {str(e)}")
                    failed_items.append(item)
        
        print(f"\nMigration completed!")
        print(f"Successfully migrated: {migrated_count} items")
        print(f"Failed items: {len(failed_items)}")
        
        if failed_items:
            print("Failed items:")
            for item in failed_items:
                print(f"  - {item.get('email', 'unknown email')}")
                
        return migrated_count, failed_items
        
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        return 0, []

# Run the migration (replace 1 with your current week number)
migrated, failed = migrate_fbp_data(current_week_number=1)
