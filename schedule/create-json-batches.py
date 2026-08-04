#!/usr/bin/env python3

import csv
import json
import math
import sys

def csv_to_dynamodb_batches(csv_file, table_name, batch_size=25):
    """
    Convert CSV to multiple DynamoDB batch files (25 items each)
    """
    
    all_items = []
    
    # Read all CSV data
    with open(csv_file, 'r') as file:
        csv_reader = csv.DictReader(file)
        numericFields=["Week", "AwayScore", "HomeScore", "Spread", "FinalWithSpread"] 
        for row in csv_reader:
            item = {}
            for key, value in row.items():
                if key in numericFields:
                            item[key] = {"N": str(value)}
                else:
                            item[key] = {"S": str(value)}
            
            put_request = {
                "PutRequest": {
                    "Item": item
                }
            }
            all_items.append(put_request)
    
    # Split into batches and create separate files
    num_batches = math.ceil(len(all_items) / batch_size)
    
    for i in range(num_batches):
        start_idx = i * batch_size
        end_idx = min((i + 1) * batch_size, len(all_items))
        batch_items = all_items[start_idx:end_idx]
        
        batch_json = {
            table_name: batch_items
        }
        
        filename = f'batch_{i+1:03d}.json'
        with open(filename, 'w') as outfile:
            json.dump(batch_json, outfile, indent=2)
        
        print(f"Created {filename} with {len(batch_items)} items")
    
    return num_batches

# Usage with your table name
csv_file=""
table_name="2025-Schedule"
if len(sys.argv) > 1:
    csv_file = sys.argv[1]
else:
    print(f"Usage: {sys.argv[0]} <csv_file>")
    sys.exit(1)

print(f"Converting {csv_file} to DynamoDB batches...")
print(f"Make sure to change the input file name and the table name")
num_files = csv_to_dynamodb_batches(csv_file, table_name)
print(f"Created {num_files} batch files for table: {table_name}")
print(f"You can now run ./import-json-batches.sh to import the weekly schedule data into DynamoDB.")