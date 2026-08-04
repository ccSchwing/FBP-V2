from decimal import Decimal
from typing import Any, Dict, Optional, Union

NumberLike = Union[int, float, Decimal]

def dynamo_number_to_int(value: Any, default: int = 0) -> int:
    """
    Convert DynamoDB number representations to int.
    Handles:
      - raw Dynamo JSON: {"N": "7"}
      - boto3 Decimal
      - plain int/float
      - numeric string
    Returns `default` on failure.
    """
    if value is None:
        return default

    # raw Dynamo JSON
    if isinstance(value, dict):
        n = value.get("N")
        if isinstance(n, (str, int, float, Decimal)):
            try:
                return int(Decimal(str(n)))
            except Exception:
                return default
        return default

    # boto3 Decimal
    if isinstance(value, Decimal):
        try:
            return int(value)
        except Exception:
            return default

    # plain numeric types or numeric strings
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return default
    if isinstance(value, str):
        try:
            return int(Decimal(value))
        except Exception:
            return default

    return default
