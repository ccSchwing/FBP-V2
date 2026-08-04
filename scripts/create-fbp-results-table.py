import boto3
from decimal import Decimal
import json

def create_fbp_results_2025_table():
    """
    Create the FBP-Results-2025 table with composite primary key and GSI
    """
    dynamodb = boto3.resource('dynamodb')
    
    try:
        table = dynamodb.create_table(
            TableName='FBP-Weekly-Results-2025',
            KeySchema=[
                {
                    'AttributeName': 'email',
                    'KeyType': 'HASH'  # Partition key
                },
                {
                    'AttributeName': 'week',
                    'KeyType': 'RANGE'  # Sort key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'email',
                    'AttributeType': 'S'
                },
                {
                    'AttributeName': 'week',
                    'AttributeType': 'N'
                }
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'WeekIndex',
                    'KeySchema': [
                        {
                            'AttributeName': 'week',
                            'KeyType': 'HASH'  # GSI Partition key
                        },
                        {
                            'AttributeName': 'email',
                            'KeyType': 'RANGE'  # GSI Sort key
                        }
                    ],
                    'Projection': {
                        'ProjectionType': 'ALL'
                    }
                    # Remove BillingMode from GSI - it inherits from table
                }
            ],
            BillingMode='PAY_PER_REQUEST'  # On-demand pricing for table and GSI
        )
        
        # Wait for table to be created
        print("Creating table FBP-Results-2025...")
        table.wait_until_exists()
        print("Table created successfully!")
        
        return table
        
    except Exception as e:
        print(f"Error creating table: {str(e)}")
        return None

# Create the table
new_table = create_fbp_results_2025_table()
