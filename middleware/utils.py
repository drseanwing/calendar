"""
Utility Functions Module
Common utility functions used across the application
Includes datetime parsing, text sanitization, UID generation, etc.
"""

import re
import uuid
import hashlib
import logging
from typing import Optional, Union, Any
from datetime import datetime
from dateutil import parser as date_parser
import pytz

from config import Config

logger = logging.getLogger(__name__)


def parse_datetime(
    dt_input: Union[str, dict, datetime, None],
    timezone: str = None
) -> Optional[datetime]:
    """
    Parse various datetime formats into timezone-aware datetime objects
    Handles M365 datetime format, ISO strings, and datetime objects
    
    Args:
        dt_input: Datetime input in various formats
        timezone: Timezone string (defaults to Config.TIMEZONE)
        
    Returns:
        Timezone-aware datetime object or None if parsing fails
        
    Examples:
        >>> parse_datetime("2024-01-15T10:30:00")
        datetime(2024, 1, 15, 10, 30, 0, tzinfo=<DstTzInfo 'Australia/Brisbane' AEST+10:00:00 STD>)
        
        >>> parse_datetime({"dateTime": "2024-01-15T10:30:00", "timeZone": "Pacific Standard Time"})
        datetime(2024, 1, 15, 10, 30, 0, tzinfo=...)
    """
    if dt_input is None:
        return None
    
    tz = pytz.timezone(timezone or Config.TIMEZONE)
    
    try:
        # Handle M365 datetime format (dict with dateTime and timeZone)
        if isinstance(dt_input, dict):
            dt_string = dt_input.get('dateTime')
            tz_string = dt_input.get('timeZone')
            
            if not dt_string:
                logger.warning(f"Dict datetime missing 'dateTime' field: {dt_input}")
                return None
            
            # Parse the datetime string
            dt = date_parser.parse(dt_string)
            
            # Try to handle M365 timezone names
            if tz_string:
                try:
                    # Map common M365 timezone names to IANA timezones
                    tz_map = {
                        'Pacific Standard Time': 'America/Los_Angeles',
                        'Mountain Standard Time': 'America/Denver',
                        'Central Standard Time': 'America/Chicago',
                        'Eastern Standard Time': 'America/New_York',
                        'GMT Standard Time': 'Europe/London',
                        'AUS Eastern Standard Time': 'Australia/Sydney',
                        'E. Australia Standard Time': 'Australia/Brisbane',
                    }
                    
                    iana_tz = tz_map.get(tz_string, tz_string)
                    tz = pytz.timezone(iana_tz)
                    
                except Exception as e:
                    logger.warning(f"Could not parse timezone '{tz_string}': {e}")
            
            # Localize or convert to target timezone
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            else:
                dt = dt.astimezone(tz)
            
            return dt
        
        # Handle datetime object
        elif isinstance(dt_input, datetime):
            if dt_input.tzinfo is None:
                return tz.localize(dt_input)
            else:
                return dt_input.astimezone(tz)
        
        # Handle string
        elif isinstance(dt_input, str):
            dt = date_parser.parse(dt_input)
            
            if dt.tzinfo is None:
                return tz.localize(dt)
            else:
                return dt.astimezone(tz)
        
        else:
            logger.warning(f"Unsupported datetime input type: {type(dt_input)}")
            return None
            
    except Exception as e:
        logger.error(f"Error parsing datetime '{dt_input}': {e}")
        return None


def generate_caldav_uid(source_id: str, source_event_id: str) -> str:
    """
    Generate a unique CalDAV UID from source information
    Format: {hash}@{source_id}.caldav
    
    Args:
        source_id: Source calendar identifier
        source_event_id: Source event identifier
        
    Returns:
        CalDAV UID string
        
    Examples:
        >>> generate_caldav_uid("m365-tenant1", "AAMkAGI2...")
        "a5f3c2b1@m365-tenant1.caldav"
    """
    # Create a deterministic hash of the source event ID
    # This ensures the same source event always gets the same CalDAV UID
    hash_input = f"{source_id}:{source_event_id}"
    hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
    
    # Clean source_id for use in UID
    clean_source = re.sub(r'[^a-zA-Z0-9-]', '', source_id)
    
    uid = f"{hash_digest}@{clean_source}.caldav"
    
    logger.debug(f"Generated CalDAV UID: {uid} for {source_id}:{source_event_id}")
    
    return uid


def sanitize_text(text: Union[str, dict, None], max_length: int = None) -> str:
    """
    Sanitize text input for safe storage and display
    Handles M365 HTML body content and other text formats
    
    Args:
        text: Text to sanitize (string or dict with 'content' field)
        max_length: Maximum length (optional)
        
    Returns:
        Sanitized text string
        
    Examples:
        >>> sanitize_text({"content": "<html><body>Test</body></html>", "contentType": "html"})
        "Test"
        
        >>> sanitize_text("  Multiple   spaces  ")
        "Multiple spaces"
    """
    if text is None:
        return ""
    
    # Handle M365 body format (dict with content and contentType)
    if isinstance(text, dict):
        content = text.get('content', '')
        content_type = text.get('contentType', 'text')
        
        # Strip HTML if content type is HTML
        if content_type.lower() == 'html':
            content = strip_html(content)
        
        text = content
    
    # Convert to string
    text = str(text)
    
    # Remove control characters except newlines and tabs
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    
    # Trim
    text = text.strip()
    
    # Truncate if max_length specified
    if max_length and len(text) > max_length:
        text = text[:max_length-3] + '...'
    
    return text


def strip_html(html: str) -> str:
    """
    Strip HTML tags from text
    Simple implementation - for production consider using bleach or html2text
    
    Args:
        html: HTML string
        
    Returns:
        Plain text string
    """
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', html)
    
    # Decode common HTML entities
    entities = {
        '&nbsp;': ' ',
        '&lt;': '<',
        '&gt;': '>',
        '&amp;': '&',
        '&quot;': '"',
        '&#39;': "'",
        '&mdash;': '—',
        '&ndash;': '–',
    }
    
    for entity, char in entities.items():
        text = text.replace(entity, char)
    
    return text


def validate_api_key(provided_key: str) -> bool:
    """
    Validate API key against configured keys
    
    Args:
        provided_key: API key from request
        
    Returns:
        True if valid, False otherwise
    """
    if not provided_key:
        return False
    
    return provided_key in Config.API_KEYS


def generate_request_id() -> str:
    """
    Generate a unique request ID for tracing
    
    Returns:
        UUID string
    """
    return str(uuid.uuid4())


def format_duration(milliseconds: int) -> str:
    """
    Format duration in milliseconds to human-readable string
    
    Args:
        milliseconds: Duration in milliseconds
        
    Returns:
        Formatted string (e.g., "1.23s", "456ms")
        
    Examples:
        >>> format_duration(1234)
        "1.23s"
        
        >>> format_duration(456)
        "456ms"
    """
    if milliseconds >= 1000:
        seconds = milliseconds / 1000
        return f"{seconds:.2f}s"
    else:
        return f"{milliseconds}ms"


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    Truncate string to maximum length with suffix
    
    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix to add when truncated
        
    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


def safe_dict_get(data: dict, path: str, default: Any = None) -> Any:
    """
    Safely get nested dict value using dot notation
    
    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., 'user.email.address')
        default: Default value if path not found
        
    Returns:
        Value at path or default
        
    Examples:
        >>> safe_dict_get({'user': {'name': 'John'}}, 'user.name')
        'John'
        
        >>> safe_dict_get({'user': {'name': 'John'}}, 'user.email', 'N/A')
        'N/A'
    """
    try:
        value = data
        for key in path.split('.'):
            value = value[key]
        return value
    except (KeyError, TypeError, AttributeError):
        return default


def is_event_in_future(event_start: datetime, days_ahead: int = 0) -> bool:
    """
    Check if event is in the future (optionally within N days)
    
    Args:
        event_start: Event start datetime
        days_ahead: Number of days ahead to consider (0 = any future event)
        
    Returns:
        True if event is in future range
    """
    from datetime import timedelta
    
    now = datetime.now(event_start.tzinfo)
    
    if days_ahead == 0:
        return event_start > now
    else:
        max_future = now + timedelta(days=days_ahead)
        return now < event_start <= max_future


def is_event_in_past(event_end: datetime, days_ago: int = 0) -> bool:
    """
    Check if event is in the past (optionally within last N days)
    
    Args:
        event_end: Event end datetime
        days_ago: Number of days ago to consider (0 = any past event)
        
    Returns:
        True if event is in past range
    """
    from datetime import timedelta
    
    now = datetime.now(event_end.tzinfo)
    
    if days_ago == 0:
        return event_end < now
    else:
        min_past = now - timedelta(days=days_ago)
        return min_past <= event_end < now


def log_dict_diff(old_dict: dict, new_dict: dict, prefix: str = "") -> list:
    """
    Generate list of differences between two dictionaries
    Useful for conflict resolution logging
    
    Args:
        old_dict: Original dictionary
        new_dict: New dictionary
        prefix: Prefix for nested keys
        
    Returns:
        List of difference strings
    """
    differences = []
    
    all_keys = set(old_dict.keys()) | set(new_dict.keys())
    
    for key in all_keys:
        full_key = f"{prefix}.{key}" if prefix else key
        
        if key not in old_dict:
            differences.append(f"Added: {full_key} = {new_dict[key]}")
        elif key not in new_dict:
            differences.append(f"Removed: {full_key} = {old_dict[key]}")
        elif old_dict[key] != new_dict[key]:
            old_val = old_dict[key]
            new_val = new_dict[key]
            
            # Recursively handle nested dicts
            if isinstance(old_val, dict) and isinstance(new_val, dict):
                differences.extend(log_dict_diff(old_val, new_val, full_key))
            else:
                differences.append(f"Changed: {full_key} from {old_val} to {new_val}")
    
    return differences


def get_timezone_offset(timezone_name: str) -> str:
    """
    Get timezone offset string (e.g., "+10:00")
    
    Args:
        timezone_name: IANA timezone name
        
    Returns:
        Offset string
    """
    try:
        tz = pytz.timezone(timezone_name)
        now = datetime.now(tz)
        offset = now.strftime('%z')
        # Format as +HH:MM
        return f"{offset[:3]}:{offset[3:]}"
    except Exception as e:
        logger.warning(f"Could not get timezone offset for {timezone_name}: {e}")
        return "+00:00"
