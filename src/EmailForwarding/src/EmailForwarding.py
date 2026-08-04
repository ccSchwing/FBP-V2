from ast import parse
from email.utils import parseaddr
from math import log
import os
import boto3
import json
import email
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import logging
from fbplib import fbpLog

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    logger.info(f"EVENT: {json.dumps(event)}")
    # Configuration
    FORWARD_TO_EMAIL = "chuckschwing@proton.me"
    FROM_EMAIL = "fbpadmin@my-fbp.com"  # Your verified SES identity
    logger.info(f"Forwarding to: {FORWARD_TO_EMAIL}")
    logger.info(f"Forwarding from: {FROM_EMAIL}")
    my_bucket = os.environ.get('SESBucketName')
    S3_REGION='us-east-1' 
    s3_client = boto3.client('s3', region_name=S3_REGION)
    ses_client = boto3.client('ses', region_name=S3_REGION)
    s3_key_prefix='inbound'
    
    try:
        # Get the SES notification from the event
        record=event['Records'][0]
        object_key=record['ses']['mail']['messageId']
        logger.info(f"Retrieving object: {record['ses']['mail']['messageId']}")
        logger.info(f"Object key: {object_key}")
        logger.info(f"Bucket: {my_bucket}")
        emailObject = s3_client.get_object(Bucket=my_bucket, Key=f"{s3_key_prefix}/{record['ses']['mail']['messageId']}")
        raw_email= emailObject['Body'].read()
        msg=email.message_from_bytes(raw_email)
        original_from=msg['From']
        reply_to=msg['Reply-to']
        if not reply_to:
            reply_to = original_from
        return_path= msg['Return-Path']
        if not return_path:
            return_path = reply_to
        del msg['DKIM-Signature']
        del msg['Sender']
        recipient_found=False
        for recipient in record['ses']['receipt']['recipients']:
            del msg['From']
            del msg['Return-Path']
            del msg['Reply-to']
            verified_from_email=FROM_EMAIL # fbpadmin@fbp.com
            from_tuple=parseaddr(verified_from_email)
            from_name=from_tuple[1]
            if not from_name:
                from_name="FBP Admin"
            msg['From'] = f"{from_name} <{verified_from_email}>"
            msg['Reply-to'] = reply_to
            forward_to = FORWARD_TO_EMAIL
            recipient_found=True
            if recipient_found:
                logger.info(f"Found recipient {recipient} in message {record['ses']['mail']['messageId']}")
                msg['To'] = forward_to
                msg['Return-Path'] = return_path
                # Send the email using SES
                response = ses_client.send_raw_email(
                    Source=verified_from_email,
                    Destinations=[forward_to],
                    RawMessage={
                        'Data': msg.as_string()
                    }
                )
                logger.info(f"Email forwarded successfully. Message ID: {response['MessageId']}")
                return {
                    'statusCode': 200,
                    'body': json.dumps('Email forwarded successfully')
                }
        
        logger.info(f"Email forwarded successfully to {FORWARD_TO_EMAIL}")
        return {'statusCode': 200, 'body': 'Email forwarded successfully'}
        
    except Exception as e:
        fbpLog("fbpadmin@my-fbp.com", "EmailForwarding", f"Error forwarding email: {str(e)}", "ERROR")
        logger.error(f"Error forwarding email: {str(e)}")
        raise e
