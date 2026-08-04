from decimal import Decimal

# This function is used to convert Decimal objects to int or float when serializing to JSON.
def decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")