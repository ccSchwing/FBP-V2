import boto3
import pandas as pd
import os
import json
from datetime import datetime
from decimal import Decimal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def clean_dynamodb_dataframe(df):
    """Clean DynamoDB DataFrame by converting Decimals"""
    
    def convert_value(val):
        if isinstance(val, Decimal):
            if val % 1 == 0:
                return int(val)
            else:
                return float(val)
        return val
    
    return df.apply(convert_value)

def export_dynamodb_to_kb(event, context):
    """
    Export DynamoDB tables to CSV and sync with Knowledge Base
    Perfect for your closePool pipeline!
    """
    
    try:
        # Step 1: Export DynamoDB tables to CSV
        csv_files = export_tables_to_csv()
        if not csv_files:
            logger.warning("No CSV files were exported from DynamoDB tables.")
            return {
                'statusCode': 404,
                'body': json.dumps({'message': 'No CSV files were exported from DynamoDB tables.'})
            }

        logger.info(f"Exported CSV files: {csv_files}")
        
        # Step 2: Upload CSVs to S3
        upload_csvs_to_s3(csv_files)
        
        # Step 3: Trigger KB sync
        sync_knowledge_base()
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Successfully exported DynamoDB data to Knowledge Base',
                'files_exported': len(csv_files)
            })
        }
        
    except Exception as e:
        logger.error(f"Error in DynamoDB export: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }

def create_metadata_file(csv_filename, content_fields, include_fields, exclude_fields):
    """Create metadata.json for CSV field control"""
    
    metadata = {
        "metadataAttributes": {
            "source": "football_app",
            "export_date": datetime.now().isoformat()
        },
        "documentStructureConfiguration": {
            "type": "RECORD_BASED_STRUCTURE_METADATA",
            "recordBasedStructureMetadata": {
                "contentFields": [{"fieldName": field} for field in content_fields],
                "metadataFieldsSpecification": {
                    "fieldsToInclude": [{"fieldName": field} for field in include_fields],
                    "fieldsToExclude": [{"fieldName": field} for field in exclude_fields]
                }
            }
        }
    }
    
    metadata_filename = f"{csv_filename}.metadata.json"
    with open(metadata_filename, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    return metadata_filename


def export_tables_to_csv():
    """Export DynamoDB tables to CSV files"""
    
    dynamodb = boto3.resource('dynamodb')
    
    # Define your Football app tables
    tables_to_export = [
        {
            'table_name': '2025-Record',
            'filename': '2025-Record',
            'privacy_level': 'public'
        },
        {
            'table_name': 'FBP-Picks', 
            'filename': 'FBP-Picks',
            'privacy_level': 'private'
        },
        {
            'table_name': 'FBP-Users',
            'filename': 'FBP-Users',
            'privacy_level': 'private'
        },
        {
            'table_name': 'FBP-Weekly-Results-2025',
            'filename': 'FBP-Weekly-Results-2025',
            'privacy_level': 'private'
        },
        {
            'table_name': '2025-Schedule', 
            'filename': '2025-Schedule',
            'privacy_level': 'private'
        }
    ]
    
    csv_files = []
    
    for table_config in tables_to_export:
        try:
            table_name = table_config['table_name']
            filename = table_config['filename']
            
            logger.info(f"Exporting table: {table_name}")
            
            # Get DynamoDB table
            table = dynamodb.Table(table_name)
            
            # Scan entire table (use pagination for large tables)
            items = scan_table_completely(table)
            
            if items:
                # Convert to DataFrame
                df = pd.DataFrame(items)
                
                # Handle Decimal types (DynamoDB specific)
                df = clean_dynamodb_dataframe(df)
                
                # Drop any NaN column names (caused by inconsistent keys across DynamoDB items)
                df = df[[col for col in df.columns if isinstance(col, str)]]
                
                csv_filename = f"/tmp/{filename}.csv"
                metadata_filename = None
                
                match table_name:
                    case '2025-Record':
                        # Public tables: include all fields
                        metadata_filename = create_metadata_file(
                            csv_filename=csv_filename,
                            content_fields=list(df.columns),
                            include_fields=list(df.columns),
                            exclude_fields=[]
                        )
                        logger.info(f"Created metadata file: {metadata_filename}")
                    case 'FBP-Picks':
                        # Private tables: exclude sensitive fields
                        sensitive_fields = ['email', 'tieBreaker','Winner']
                        include_fields = [field for field in df.columns if field not in sensitive_fields]
                        df=df[include_fields]
                        metadata_filename = create_metadata_file(
                            csv_filename=csv_filename,
                            content_fields=list(df.columns),
                            include_fields=include_fields,
                            exclude_fields=sensitive_fields
                        )
                        logger.info(f"Created metadata file: {metadata_filename}")
                    case 'FBP-Users':
                        # Private tables: exclude sensitive fields
                        sensitive_fields = ['email', 'firstName', 'lastName', 'beta', 'Winner', 'mobile_number', 'verification_code', 'verification_code_hash']
                        content_fields = ['displayName']
                        include_fields = [field for field in df.columns if field not in sensitive_fields]
                        df=df[include_fields]
                        metadata_filename = create_metadata_file(
                            csv_filename=csv_filename,
                            content_fields=content_fields,
                            include_fields=include_fields,
                            exclude_fields=sensitive_fields
                        )
                        logger.info(f"Created metadata file: {metadata_filename}")
                    case 'FBP-Weekly-Results-2025':
                        # Private tables: exclude sensitive fields
                        sensitive_fields = ['email']
                        include_fields = [field for field in df.columns if field not in sensitive_fields]
                        df=df[include_fields]
                        metadata_filename = create_metadata_file(
                            csv_filename=csv_filename,
                            content_fields=list(df.columns),
                            include_fields=include_fields,
                            exclude_fields=sensitive_fields
                        )
                        logger.info(f"Created metadata file: {metadata_filename}")
                    case '2025-Schedule':
                        # Public tables: include all fields
                        sensitive_fields = ['FinalWithSpread', 'GameId']
                        include_fields = [field for field in df.columns if field not in sensitive_fields]
                        df=df[include_fields]
                        metadata_filename = create_metadata_file(
                            csv_filename=csv_filename,
                            content_fields=['Week', 'Home', 'Away'],
                            include_fields=list(df.columns),
                            exclude_fields=sensitive_fields
                        )
                        logger.info(f"Created metadata file: {metadata_filename}")
                    case _:
                        logger.warning(f"No metadata handling defined for table: {table_name}")
                        return None
                        
                
                # Save as CSV
                df.to_csv(csv_filename, index=False)
                csv_files.append(csv_filename)
                if metadata_filename:
                    csv_files.append(metadata_filename)
                logger.info(f"Exported {len(items)} records from {table_name} to {csv_filename} with metadata {metadata_filename}") 
                logger.info(f"Exported {len(items)} records from {table_name}")
            else:
                logger.warning(f"No data found in table: {table_name}")
                
        except Exception as e:
            logger.error(f"Error exporting table {table_name}: {str(e)}")
            #continue
            return None
    
    return csv_files

def scan_table_completely(table):
    """Scan DynamoDB table with pagination"""
    
    items = []
    
    # Initial scan
    response = table.scan()
    items.extend(response['Items'])
    
    # Handle pagination
    while 'LastEvaluatedKey' in response:
        response = table.scan(
            ExclusiveStartKey=response['LastEvaluatedKey']
        )
        items.extend(response['Items'])
    
    return items

def upload_csvs_to_s3(csv_files):
    """Upload CSV files to S3 bucket"""
    
    s3 = boto3.client('s3')
    bucket_name = os.environ['S3BucketName']
    
    for csv_file in csv_files:
        try:
            filename = os.path.basename(csv_file)
            s3_key = f"FBP-KB/{filename}"
            
            # Upload file
            s3.upload_file(csv_file, bucket_name, s3_key)
            logger.info(f"Uploaded {filename} to S3: s3://{bucket_name}/{s3_key}")
            
            # Clean up temp file
            os.remove(csv_file)
            
        except Exception as e:
            logger.error(f"Error uploading {csv_file}: {str(e)}")

def sync_knowledge_base():
    """Trigger Knowledge Base sync"""
    
    bedrock_agent = boto3.client('bedrock-agent')
    
    try:
        response = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=os.environ['KnowledgeBaseId'],
            dataSourceId=os.environ['DataSourceId']
        )
        
        job_id = response['ingestionJob']['ingestionJobId']
        logger.info(f"Knowledge Base sync started: {job_id}")
        
        return job_id
        
    except Exception as e:
        logger.error(f"Error starting KB sync: {str(e)}")
        raise
