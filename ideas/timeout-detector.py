import signal

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Function is about to timeout!")

def openPool(event, context):
    # Set alarm for 10 seconds before Lambda timeout
    signal_time = max(0, (context.get_remaining_time_in_millis() - 10000) // 1000)
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(signal_time)
    
    try:
        # ... your existing code ...
    except TimeoutError as e:
        print(f"ERROR: {str(e)}")
        # Send SNS alert, log to DLQ, etc.
        return {"statusCode": 500, "body": "Function timed out gracefully"}
    finally:
        signal.alarm(0)  # Cancel the alarm
