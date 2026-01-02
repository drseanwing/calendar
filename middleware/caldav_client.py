"""
CalDAV Client Module
Handles all interactions with the Baikal CalDAV server
Provides methods for creating, updating, and deleting calendar events
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime
from urllib.parse import urljoin

import caldav
from caldav import DAVClient, Calendar, Event
from caldav.lib.error import DAVError, NotFoundError
from icalendar import Calendar as iCalendar, Event as iEvent
from icalendar import vDatetime, vText
import pytz

from config import Config

logger = logging.getLogger(__name__)


class CalDAVClient:
    """
    Wrapper around caldav library for Baikal server interactions
    Provides robust error handling and retry logic
    """
    
    def __init__(self, url: str = None, username: str = None, password: str = None):
        """
        Initialize CalDAV client
        
        Args:
            url: CalDAV server URL (defaults to Config.CALDAV_URL)
            username: CalDAV username (defaults to Config.CALDAV_USERNAME)
            password: CalDAV password (defaults to Config.CALDAV_PASSWORD)
        """
        self.url = url or Config.CALDAV_URL
        self.username = username or Config.CALDAV_USERNAME
        self.password = password or Config.CALDAV_PASSWORD
        self.timeout = Config.CALDAV_TIMEOUT
        self.retry_attempts = Config.CALDAV_RETRY_ATTEMPTS
        self.retry_delay = Config.CALDAV_RETRY_DELAY
        
        self._client: Optional[DAVClient] = None
        self._calendar: Optional[Calendar] = None
        
        logger.info(f"CalDAV client initialized for URL: {self.url}")
    
    def _get_client(self) -> DAVClient:
        """
        Get or create DAVClient instance with connection pooling
        
        Returns:
            DAVClient instance
        """
        if self._client is None:
            logger.debug(f"Creating new DAVClient for {self.url}")
            self._client = DAVClient(
                url=self.url,
                username=self.username,
                password=self.password,
                timeout=self.timeout
            )
        return self._client
    
    def _get_calendar(self, calendar_name: str = None) -> Calendar:
        """
        Get calendar by name or use default
        
        Args:
            calendar_name: Name of calendar to retrieve
            
        Returns:
            Calendar instance
            
        Raises:
            ValueError: If calendar not found
        """
        calendar_name = calendar_name or Config.CALDAV_CALENDAR_NAME
        
        if self._calendar is None or self._calendar.name != calendar_name:
            logger.debug(f"Looking up calendar: {calendar_name}")
            
            client = self._get_client()
            principal = client.principal()
            calendars = principal.calendars()
            
            for cal in calendars:
                if cal.name == calendar_name:
                    self._calendar = cal
                    logger.info(f"Found calendar: {calendar_name} at {cal.url}")
                    return self._calendar
            
            raise ValueError(f"Calendar '{calendar_name}' not found on server")
        
        return self._calendar
    
    def _retry_operation(self, operation, *args, **kwargs):
        """
        Retry an operation with exponential backoff
        
        Args:
            operation: Function to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation
            
        Returns:
            Result of operation
            
        Raises:
            Last exception if all retries fail
        """
        last_exception = None
        
        for attempt in range(self.retry_attempts):
            try:
                return operation(*args, **kwargs)
            except (DAVError, ConnectionError, TimeoutError) as e:
                last_exception = e
                if attempt < self.retry_attempts - 1:
                    delay = self.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(
                        f"Operation failed (attempt {attempt + 1}/{self.retry_attempts}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Operation failed after {self.retry_attempts} attempts: {e}")
        
        raise last_exception
    
    def create_event(
        self,
        uid: str,
        summary: str,
        start: datetime,
        end: datetime,
        description: str = None,
        location: str = None,
        is_all_day: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create a new calendar event
        
        Args:
            uid: Unique identifier for the event (CalDAV UID)
            summary: Event title/subject
            start: Start datetime
            end: End datetime
            description: Event description/body
            location: Event location
            is_all_day: Whether event is all-day
            **kwargs: Additional event properties
            
        Returns:
            Dictionary with event details including URL and ETag
            
        Raises:
            DAVError: If creation fails
        """
        logger.info(f"Creating event: UID={uid}, Summary={summary}")
        
        # Build iCalendar event
        cal = iCalendar()
        event = iEvent()
        
        event.add('uid', uid)
        event.add('summary', summary)
        
        # Handle timezone-aware datetimes
        tz = pytz.timezone(Config.TIMEZONE)
        if not start.tzinfo:
            start = tz.localize(start)
        if not end.tzinfo:
            end = tz.localize(end)
        
        if is_all_day:
            # For all-day events, use DATE instead of DATETIME
            event.add('dtstart', start.date())
            event.add('dtend', end.date())
        else:
            event.add('dtstart', start)
            event.add('dtend', end)
        
        if description:
            event.add('description', description)
        
        if location:
            event.add('location', location)
        
        # Add additional properties
        event.add('dtstamp', datetime.now(tz))
        event.add('created', datetime.now(tz))
        event.add('last-modified', datetime.now(tz))
        
        # Add any extra properties from kwargs
        for key, value in kwargs.items():
            if key not in ['uid', 'summary', 'dtstart', 'dtend', 'description', 'location']:
                event.add(key, value)
        
        cal.add_component(event)
        
        # Create event on CalDAV server
        def _create():
            calendar = self._get_calendar()
            caldav_event = calendar.save_event(cal.to_ical().decode('utf-8'))
            return caldav_event
        
        caldav_event = self._retry_operation(_create)
        
        logger.info(f"Event created successfully: UID={uid}, URL={caldav_event.url}")
        
        return {
            'uid': uid,
            'url': str(caldav_event.url),
            'etag': caldav_event.etag if hasattr(caldav_event, 'etag') else None,
            'icalendar': cal.to_ical().decode('utf-8')
        }
    
    def update_event(
        self,
        uid: str,
        summary: str = None,
        start: datetime = None,
        end: datetime = None,
        description: str = None,
        location: str = None,
        is_all_day: bool = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event
        
        Args:
            uid: Event UID to update
            summary: New event title (optional)
            start: New start datetime (optional)
            end: New end datetime (optional)
            description: New description (optional)
            location: New location (optional)
            is_all_day: New all-day status (optional)
            **kwargs: Additional properties to update
            
        Returns:
            Dictionary with updated event details
            
        Raises:
            NotFoundError: If event not found
            DAVError: If update fails
        """
        logger.info(f"Updating event: UID={uid}")
        
        # Find existing event
        def _find_event():
            calendar = self._get_calendar()
            events = calendar.search(uid=uid)
            if not events:
                raise NotFoundError(f"Event with UID {uid} not found")
            return events[0]
        
        caldav_event = self._retry_operation(_find_event)
        
        # Parse existing event data
        existing_cal = iCalendar.from_ical(caldav_event.data)
        existing_event = None
        for component in existing_cal.walk():
            if component.name == "VEVENT":
                existing_event = component
                break
        
        if not existing_event:
            raise ValueError(f"No VEVENT found in event {uid}")
        
        # Update properties (only if new values provided)
        if summary is not None:
            existing_event['summary'] = summary
        
        tz = pytz.timezone(Config.TIMEZONE)
        
        if start is not None:
            if not start.tzinfo:
                start = tz.localize(start)
            if is_all_day:
                existing_event['dtstart'] = vDatetime(start.date())
            else:
                existing_event['dtstart'] = vDatetime(start)
        
        if end is not None:
            if not end.tzinfo:
                end = tz.localize(end)
            if is_all_day:
                existing_event['dtend'] = vDatetime(end.date())
            else:
                existing_event['dtend'] = vDatetime(end)
        
        if description is not None:
            existing_event['description'] = vText(description)
        
        if location is not None:
            existing_event['location'] = vText(location)
        
        # Update last-modified timestamp
        existing_event['last-modified'] = vDatetime(datetime.now(tz))
        
        # Update additional properties
        for key, value in kwargs.items():
            existing_event[key] = value
        
        # Save updated event
        def _update():
            caldav_event.data = existing_cal.to_ical().decode('utf-8')
            caldav_event.save()
            return caldav_event
        
        updated_event = self._retry_operation(_update)
        
        logger.info(f"Event updated successfully: UID={uid}")
        
        return {
            'uid': uid,
            'url': str(updated_event.url),
            'etag': updated_event.etag if hasattr(updated_event, 'etag') else None,
            'icalendar': existing_cal.to_ical().decode('utf-8')
        }
    
    def delete_event(self, uid: str) -> bool:
        """
        Delete a calendar event
        
        Args:
            uid: Event UID to delete
            
        Returns:
            True if deleted successfully
            
        Raises:
            NotFoundError: If event not found
            DAVError: If deletion fails
        """
        logger.info(f"Deleting event: UID={uid}")
        
        def _delete():
            calendar = self._get_calendar()
            events = calendar.search(uid=uid)
            if not events:
                raise NotFoundError(f"Event with UID {uid} not found")
            
            event = events[0]
            event.delete()
            return True
        
        result = self._retry_operation(_delete)
        
        logger.info(f"Event deleted successfully: UID={uid}")
        return result
    
    def get_event(self, uid: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve event by UID
        
        Args:
            uid: Event UID
            
        Returns:
            Dictionary with event data or None if not found
        """
        logger.debug(f"Retrieving event: UID={uid}")
        
        try:
            def _get():
                calendar = self._get_calendar()
                events = calendar.search(uid=uid)
                return events[0] if events else None
            
            caldav_event = self._retry_operation(_get)
            
            if not caldav_event:
                return None
            
            # Parse event data
            cal = iCalendar.from_ical(caldav_event.data)
            for component in cal.walk():
                if component.name == "VEVENT":
                    return {
                        'uid': str(component.get('uid')),
                        'summary': str(component.get('summary', '')),
                        'start': component.get('dtstart').dt,
                        'end': component.get('dtend').dt,
                        'description': str(component.get('description', '')),
                        'location': str(component.get('location', '')),
                        'url': str(caldav_event.url),
                        'etag': caldav_event.etag if hasattr(caldav_event, 'etag') else None,
                        'icalendar': caldav_event.data
                    }
            
            return None
            
        except NotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error retrieving event {uid}: {e}")
            return None
    
    def list_events(
        self,
        start: datetime = None,
        end: datetime = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        List events within a date range
        
        Args:
            start: Start datetime for range (optional)
            end: End datetime for range (optional)
            limit: Maximum number of events to return (optional)
            
        Returns:
            List of event dictionaries
        """
        logger.debug(f"Listing events: start={start}, end={end}, limit={limit}")
        
        def _list():
            calendar = self._get_calendar()
            
            # Build search criteria
            if start and end:
                events = calendar.date_search(start=start, end=end)
            else:
                events = calendar.events()
            
            return list(events)
        
        caldav_events = self._retry_operation(_list)
        
        results = []
        for caldav_event in caldav_events[:limit] if limit else caldav_events:
            try:
                cal = iCalendar.from_ical(caldav_event.data)
                for component in cal.walk():
                    if component.name == "VEVENT":
                        results.append({
                            'uid': str(component.get('uid')),
                            'summary': str(component.get('summary', '')),
                            'start': component.get('dtstart').dt,
                            'end': component.get('dtend').dt,
                            'url': str(caldav_event.url),
                        })
                        break
            except Exception as e:
                logger.warning(f"Error parsing event: {e}")
                continue
        
        logger.info(f"Retrieved {len(results)} events")
        return results
    
    def health_check(self) -> bool:
        """
        Check if CalDAV server is accessible
        
        Returns:
            True if server is healthy
        """
        try:
            client = self._get_client()
            principal = client.principal()
            calendars = principal.calendars()
            logger.debug(f"Health check passed: found {len(calendars)} calendars")
            return True
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
