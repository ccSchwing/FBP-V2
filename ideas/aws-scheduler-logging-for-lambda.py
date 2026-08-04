import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    # Log the full event for debugging
    logger.info(f"Lambda invoked with event: {json.dumps(event, default=str)}")
    
    # Identify the invocation source
    source = event.get('source', 'unknown')
    detail_type = event.get('detail-type', 'unknown')
    
    if source == 'aws.scheduler':
        logger.info("✅ INVOKED BY EVENTBRIDGE SCHEDULER")
        schedule_arn = event.get('resources', [None])[0]
        if schedule_arn:
            schedule_name = schedule_arn.split('/')[-1]
            logger.info(f"Schedule name: {schedule_name}")
    elif 'routeKey' in event:
        logger.info("🌐 INVOKED BY API GATEWAY (manual test)")
    else:
        logger.info(f"🔍 INVOKED BY: {source} (detail-type: {detail_type})")