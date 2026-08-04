import json
import boto3
import os
import logging
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock_agent_runtime = boto3.client('bedrock-agent-runtime')

def chatbot(event, context):
    """
    Lambda function to handle Football app chatbot queries using Bedrock Knowledge Base
    """
    
    try:
        # Parse the incoming request
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event
            
        user_question = body.get('question', '')
        session_id = body.get('sessionId', '')
        
        if not user_question:
            return create_response(400, {'error': 'Question is required'})
        
        # Your Knowledge Base ID (replace with your actual KB ID)
        knowledge_base_id = os.environ.get('KnowledgeBaseId', 'YOUR_FBP_KB_ID_HERE')
        
        # Model ARN for Nova Lite (adjust region as needed)
        region = os.environ.get('AWS_REGION', 'us-east-1')

        model_arn = f"arn:aws:bedrock:{region}::foundation-model/amazon.nova-lite-v1:0"
        response = agentic_retrieve(user_question, knowledge_base_id)
        
        # Extract the answer and sources from the streaming response
        answer = ""
        sources = []
        
        # Process the streaming response
        if 'stream' in response:
            for event in response['stream']:
            # Check for nested responseEvent structure first
                if 'responseEvent' in event and 'text' in event['responseEvent']:
                    answer += event['responseEvent']['text']
            
        # Original logic as fallback
        elif 'text' in event:
            text_data = event['text']
            if isinstance(text_data, dict):
                # If it's a dict, extract text content
                if 'text' in text_data:
                    answer += text_data['text']
                elif 'delta' in text_data and 'text' in text_data['delta']:
                    answer += text_data['delta']['text']
            else:
                # If it's a string, use directly
                answer += str(text_data)
            for event in response['stream']:
                if 'text' in event:
                    text_data = event['text']
                    if isinstance(text_data, dict):
                        # If it's a dict, extract text content
                        if 'text' in text_data:
                            answer += text_data['text']
                        elif 'delta' in text_data and 'text' in text_data['delta']:
                            answer += text_data['delta']['text']
                    else:
                        # If it's a string, use directly
                        answer += str(text_data)                
                if 'chunk' in event:
                    chunk = event['chunk']
                    if 'bytes' in chunk:
                        chunk_data = json.loads(chunk['bytes'].decode('utf-8'))
                        
                        # Extract answer text
                        if 'type' in chunk_data and chunk_data['type'] == 'response':
                            if 'delta' in chunk_data and 'text' in chunk_data['delta']:
                                answer += chunk_data['delta']['text']
                        
                        # Extract sources from result event
                        if 'type' in chunk_data and chunk_data['type'] == 'result':
                            if 'retrievalResults' in chunk_data:
                                for result in chunk_data['retrievalResults']:
                                    if 'location' in result and 's3Location' in result['location']:
                                        sources.append({
                                            'uri': result['location']['s3Location']['uri'],
                                            'content': result.get('content', {}).get('text', '')[:200] + '...'
                                        })
 
        # Return successful response
        return create_response(200, {
            'answer': answer.strip(),
            'sources': sources
        })
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return create_response(500, {
            'error': 'Internal server error',
            'message': str(e)
        }) 
        
def agentic_retrieve(question, kb_id):
    """
    Query the Managed Knowledge Base using AgenticRetrieveStream
    """
    try:
        response = bedrock_agent_runtime.agentic_retrieve_stream(
            agenticRetrieveConfiguration={
                'maxAgentIteration': 5
            },
            messages=[
                {
                    'role': 'user',
                    'content': {
                        'text': question
                    }
                }
            ],
            retrievers=[
                {
                    'description': 'Football app knowledge base',
                    'configuration': {
                        'knowledgeBase': {
                            'knowledgeBaseId': kb_id
                        }
                    }
                }
            ],
            generateResponse=True
        )
        
        logger.info(f"Successfully initiated agentic retrieve for question: {question[:50]}...")
        return response
        

    except ClientError as e:
        logger.error(f"Bedrock API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error in agentic_retrieve: {e}")
        raise


def create_response(status_code, body):
    """
    Create a properly formatted API Gateway response
    """
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',  # Adjust for your domain
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps(body)
    }

# Initialize Bedrock client

def lambda_handler(event, context):
    return chatbot(event, context)