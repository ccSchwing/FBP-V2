import json
import boto3
import os
import base64
from datetime import datetime, timezone
from urllib.parse import parse_qs
import logging
from fbplib.fbpLog import fbpLog

# Initialize outside handler for connection reuse
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TwilioOptOutTableName'])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Standard opt-out keywords (case-insensitive)
OPT_OUT_KEYWORDS = {
    'STOP', 'CANCEL', 'END', 'OPT-OUT', 'OPTOUT', 
    'QUIT', 'REMOVE', 'UNSUBSCRIBE', 'TD', 'ARRET'
}

# Opt-in keywords
OPT_IN_KEYWORDS = {'START', 'UNSTOP', 'YES'}

def cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'POST, OPTIONS'
    }

def lambda_handler(event, context):
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': cors_headers(),
            'body': ''
        }
    try:
        # For HttpApi (PayloadFormatVersion 2.0), body is directly available
        body = event.get('body', '')
        
        # Check if base64 encoded
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')        
        # Parse form data
        parsed_data = parse_qs(body)
        
        # Extract Twilio parameters
        from_number = parsed_data.get('From', [''])[0]
        message_body = parsed_data.get('Body', [''])[0].strip().upper()
        to_number = parsed_data.get('To', [''])[0]
        
        logger.info(f"Received SMS from {from_number}: {message_body}")
        
        # Normalize phone number (remove +1, etc.)
        normalized_phone = normalize_phone_number(from_number)
        
        # Check for opt-out keywords
        if message_body in OPT_OUT_KEYWORDS:
            handle_opt_out(normalized_phone, to_number, message_body)
            return create_twilio_response("You have been unsubscribed. Reply START to opt back in.")
        
        # Check for opt-in keywords
        elif message_body in OPT_IN_KEYWORDS:
            handle_opt_in(normalized_phone, to_number, message_body)
            return create_twilio_response("You have been subscribed to receive messages. Reply STOP to opt out.")
        
        # Handle other messages (optional - could forward to customer service)
        else:
            logger.info(f"Non-opt-out message received: {message_body}")
            # Optionally publish to SNS for customer service handling
            
        return create_twilio_response("")  # Empty response for non-opt-out messages
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                **cors_headers(),
                'Content-Type': 'text/plain'
            },
            'body': 'Internal server error'
        }

def normalize_phone_number(phone):
    """Normalize phone number to E.164 format"""
    # Remove all non-digits
    digits_only = ''.join(filter(str.isdigit, phone))
    
    # Add +1 if it's a US number without country code
    if len(digits_only) == 10:
        return f"+1{digits_only}"
    elif len(digits_only) == 11 and digits_only.startswith('1'):
        return f"+{digits_only}"
    else:
        return f"+{digits_only}"

def handle_opt_out(phone_number, originator, keyword):
    """Process opt-out request"""
    try:
        # Store opt-out in DynamoDB
        table.put_item(
            Item={
                'phone_number': phone_number,
                'opted_out': True,
                'opt_out_timestamp': datetime.now(timezone.utc).isoformat(),
                'opt_out_keyword': keyword,
                'originator_number': originator,
                'ttl': int((datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60))  # 1 year TTL
            }
        )
        
        logger.info(f"Successfully processed opt-out for {phone_number}")
        
    except Exception as e:
        logger.error(f"Error processing opt-out for {phone_number}: {str(e)}")
        raise

def handle_opt_in(phone_number, originator, keyword):
    """Process opt-in request"""
    try:
        # Remove from opt-out list
        table.delete_item(
            Key={'phone_number': phone_number}
        )
        
        logger.info(f"Successfully processed opt-in for {phone_number}")
        
    except Exception as e:
        logger.error(f"Error processing opt-in for {phone_number}: {str(e)}")
        raise

def create_twilio_response(message):
    """Create TwiML response for Twilio"""
    if message:
        twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{message}</Message></Response>'
    else:
        twiml = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
    
    return {
        'statusCode': 200,
        'headers': {
            **cors_headers(),
            'Content-Type': 'application/xml'
        },
        'body': twiml
    }
