import datetime

# Format datetime object as ISO string for JavaScript
def format_time_for_js(dt):
    """Convert datetime to ISO string for JavaScript"""
    if dt is None:
        return None
    try:
        return dt.isoformat() if not isinstance(dt, str) else dt
    except Exception:
        return None