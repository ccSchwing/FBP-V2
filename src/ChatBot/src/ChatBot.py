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
        
        knowledge_base_id = os.environ.get('KnowledgeBaseId', 'YOUR_FBP_KB_ID_HERE')
        
        response = agentic_retrieve(user_question, knowledge_base_id)
        
        answer = ""
        sources = []
        if 'stream' in response:
            for stream_event in response['stream']:
                
                # --- ANSWER TEXT ---
                if 'responseEvent' in stream_event:
                    answer += stream_event['responseEvent'].get('text', '')
                
                # --- SOURCES --- one traceEvent, no deduplication needed
                if 'traceEvent' in stream_event:
                    seen_uris = set()
                    for item in (stream_event
                            .get('traceEvent', {})
                            .get('attributes', {})
                            .get('retrievalResponse', [])):
                        # uri = item.get('metadata', {}).get('function variables', {}).get('_source_uri', '')
                        uri = item.get('metadata', {}).get('_source_uri', '')
                        if uri and uri not in seen_uris:
                            sources.append({'uri': uri})
                            seen_uris.add(uri)

            # Process the streaming response from agentic_retrieve_stream
                # Log any trace events for debugging (optional, remove in production)
                if 'traceEvent' in stream_event:
                    logger.info(f"Trace: {json.dumps(stream_event['traceEvent'])}")

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
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'POST, OPTIONS'
        },
        'body': json.dumps(body)
    }

def lambda_handler(event, context):
    return chatbot(event, context)
