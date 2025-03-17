import datetime

# Safely handle datetime objects with timezone information
def safe_datetime(dt):
    """Convert datetime to UTC or return None if invalid"""
    if dt is None:
        return None
        
    try:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None