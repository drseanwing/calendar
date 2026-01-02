"""
Webhook Handlers Module
Processes incoming webhooks from PowerAutomate (M365) and other sources
Handles event creation, updates, and deletions with proper error handling
"""

import logging
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import pytz

from models import SourceCalendar, EventMapping, SyncHistory, ConflictResolution
from caldav_client import CalDAVClient
from config import Config
from utils import parse_datetime, generate_caldav_uid, sanitize_text

logger = logging.getLogger(__name__)


class WebhookHandler:
    """
    Handles webhook processing for calendar events
    Implements sync logic with conflict resolution
    """
    
    def __init__(self, db_session: Session, caldav_client: CalDAVClient):
        """
        Initialize webhook handler
        
        Args:
            db_session: SQLAlchemy database session
            caldav_client: CalDAV client instance
        """
        self.db = db_session
        self.caldav = caldav_client
        self.tz = pytz.timezone(Config.TIMEZONE)
    
    def _get_or_create_source_calendar(self, source_id: str) -> SourceCalendar:
        """
        Get existing source calendar or create if not exists
        
        Args:
            source_id: Source calendar identifier
            
        Returns:
            SourceCalendar instance
        """
        source_calendar = self.db.query(SourceCalendar).filter_by(source_id=source_id).first()
        
        if not source_calendar:
            logger.info(f"Creating new source calendar: {source_id}")
            
            # Determine source type from ID
            if 'm365' in source_id.lower():
                source_type = 'microsoft365'
            elif 'icloud' in source_id.lower():
                source_type = 'icloud'
            elif 'google' in source_id.lower():
                source_type = 'google'
            else:
                source_type = 'unknown'
            
            source_calendar = SourceCalendar(
                source_id=source_id,
                source_type=source_type,
                display_name=source_id.replace('-', ' ').title(),
                priority=Config.get_source_priority(source_id),
                sync_enabled=True
            )
            self.db.add(source_calendar)
            self.db.commit()
        
        return source_calendar
    
    def _log_sync_operation(
        self,
        operation_type: str,
        status: str,
        source_calendar: SourceCalendar,
        source_event_id: str,
        caldav_uid: str = None,
        event_mapping: EventMapping = None,
        details: str = None,
        error_message: str = None,
        error_stack: str = None,
        processing_time_ms: int = None,
        webhook_source: str = None,
        request_id: str = None
    ) -> SyncHistory:
        """
        Create sync history log entry
        
        Args:
            operation_type: Type of operation ('create', 'update', 'delete')
            status: Operation status ('success', 'error', 'skipped')
            source_calendar: SourceCalendar instance
            source_event_id: Source event ID
            caldav_uid: CalDAV UID (optional)
            event_mapping: EventMapping instance (optional)
            details: Operation details (optional)
            error_message: Error message if status='error' (optional)
            error_stack: Error stack trace (optional)
            processing_time_ms: Processing time in milliseconds (optional)
            webhook_source: Source of webhook (optional)
            request_id: Request ID for tracing (optional)
            
        Returns:
            Created SyncHistory instance
        """
        history = SyncHistory(
            event_mapping_id=event_mapping.id if event_mapping else None,
            source_calendar_id=source_calendar.id,
            operation_type=operation_type,
            status=status,
            source_event_id=source_event_id,
            caldav_uid=caldav_uid,
            details=details,
            error_message=error_message,
            error_stack=error_stack,
            processing_time_ms=processing_time_ms,
            webhook_source=webhook_source,
            request_id=request_id
        )
        self.db.add(history)
        self.db.commit()
        
        logger.info(
            f"Sync operation logged: {operation_type} - {status} - "
            f"Source: {source_calendar.source_id} - Event: {source_event_id}"
        )
        
        return history
    
    def _resolve_conflict(
        self,
        event_mapping: EventMapping,
        new_data: Dict[str, Any],
        source_calendar: SourceCalendar
    ) -> Tuple[bool, str]:
        """
        Resolve conflict when event has been modified
        
        Args:
            event_mapping: Existing EventMapping
            new_data: New event data from webhook
            source_calendar: Source calendar
            
        Returns:
            Tuple of (should_update: bool, reason: str)
        """
        logger.info(f"Resolving conflict for event: {event_mapping.source_event_id}")
        
        strategy = Config.CONFLICT_RESOLUTION
        
        if strategy == 'last_write_wins':
            # Always accept the new data
            logger.debug("Conflict resolution: last_write_wins - accepting new data")
            return True, "last_write_wins"
        
        elif strategy == 'priority_based':
            # Compare priorities of source calendars
            current_priority = event_mapping.source_calendar.priority
            new_priority = source_calendar.priority
            
            if new_priority >= current_priority:
                logger.debug(
                    f"Conflict resolution: priority_based - "
                    f"new priority ({new_priority}) >= current ({current_priority})"
                )
                return True, f"priority_based (new: {new_priority}, current: {current_priority})"
            else:
                logger.debug(
                    f"Conflict resolution: priority_based - "
                    f"keeping current (priority {current_priority} > {new_priority})"
                )
                return False, f"priority_based (current priority higher)"
        
        elif strategy == 'manual':
            # Don't auto-resolve - mark for manual review
            logger.warning(
                f"Conflict resolution: manual - marking event for review: "
                f"{event_mapping.source_event_id}"
            )
            return False, "manual_review_required"
        
        else:
            # Default to last_write_wins
            logger.warning(f"Unknown conflict strategy '{strategy}', defaulting to last_write_wins")
            return True, "last_write_wins (default)"
    
    def handle_event_created(
        self,
        source_id: str,
        event_data: Dict[str, Any],
        request_id: str = None
    ) -> Dict[str, Any]:
        """
        Handle event creation webhook
        
        Args:
            source_id: Source calendar ID (e.g., 'm365-tenant1')
            event_data: Event data from webhook
            request_id: Request ID for tracing
            
        Returns:
            Dictionary with operation result
        """
        start_time = datetime.now()
        source_event_id = event_data.get('id')
        
        if not source_event_id:
            logger.error("Event data missing 'id' field")
            return {'status': 'error', 'message': "Missing required field: 'id'"}
        
        logger.info(f"Processing event creation: Source={source_id}, EventID={source_event_id}")
        
        try:
            # Get or create source calendar
            source_calendar = self._get_or_create_source_calendar(source_id)
            
            # Check if event already exists (deduplication)
            if Config.ENABLE_DEDUPLICATION:
                existing = self.db.query(EventMapping).filter_by(
                    source_calendar_id=source_calendar.id,
                    source_event_id=source_event_id
                ).first()
                
                if existing and not existing.is_deleted():
                    logger.warning(
                        f"Event already exists: {source_event_id}. "
                        f"Treating as update instead."
                    )
                    return self.handle_event_updated(source_id, event_data, request_id)
            
            # Parse event data
            summary = sanitize_text(event_data.get('subject', 'Untitled Event'))
            start = parse_datetime(event_data.get('start'))
            end = parse_datetime(event_data.get('end'))
            description = sanitize_text(event_data.get('body', ''))
            location = sanitize_text(event_data.get('location', ''))
            is_all_day = event_data.get('isAllDay', False)
            
            if not start or not end:
                raise ValueError("Event must have start and end times")
            
            # Generate CalDAV UID
            caldav_uid = generate_caldav_uid(source_id, source_event_id)
            
            # Create event in CalDAV server
            caldav_result = self.caldav.create_event(
                uid=caldav_uid,
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                is_all_day=is_all_day
            )
            
            # Create event mapping in database
            event_mapping = EventMapping(
                source_calendar_id=source_calendar.id,
                source_event_id=source_event_id,
                source_change_key=event_data.get('changeKey'),
                caldav_uid=caldav_uid,
                caldav_url=caldav_result['url'],
                caldav_etag=caldav_result.get('etag'),
                event_subject=summary,
                event_start=start,
                event_end=end,
                is_all_day=is_all_day,
                is_recurring=bool(event_data.get('recurrence')),
                recurrence_pattern=event_data.get('recurrence'),
                sync_status='synced',
                last_synced_at=datetime.utcnow(),
                last_modified_at=datetime.utcnow(),
                source_event_data=event_data,
                caldav_event_data={'icalendar': caldav_result['icalendar']}
            )
            
            self.db.add(event_mapping)
            self.db.commit()
            
            # Log successful operation
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync_operation(
                operation_type='create',
                status='success',
                source_calendar=source_calendar,
                source_event_id=source_event_id,
                caldav_uid=caldav_uid,
                event_mapping=event_mapping,
                details=f"Created event: {summary}",
                processing_time_ms=processing_time,
                webhook_source=source_id,
                request_id=request_id
            )
            
            # Update source calendar sync time
            source_calendar.last_sync_time = datetime.utcnow()
            source_calendar.sync_errors = 0
            self.db.commit()
            
            logger.info(
                f"Event created successfully: {source_event_id} -> {caldav_uid} "
                f"(took {processing_time}ms)"
            )
            
            return {
                'status': 'success',
                'operation': 'create',
                'source_event_id': source_event_id,
                'caldav_uid': caldav_uid,
                'caldav_url': caldav_result['url'],
                'processing_time_ms': processing_time
            }
            
        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Database integrity error creating event {source_event_id}: {e}")
            
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync_operation(
                operation_type='create',
                status='error',
                source_calendar=source_calendar,
                source_event_id=source_event_id,
                error_message=str(e),
                processing_time_ms=processing_time,
                webhook_source=source_id,
                request_id=request_id
            )
            
            return {
                'status': 'error',
                'operation': 'create',
                'message': 'Database integrity error (possible duplicate)',
                'source_event_id': source_event_id
            }
            
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Error creating event {source_event_id}: {e}")
            
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if source_calendar:
                source_calendar.sync_errors += 1
                self.db.commit()
                
                self._log_sync_operation(
                    operation_type='create',
                    status='error',
                    source_calendar=source_calendar,
                    source_event_id=source_event_id,
                    error_message=str(e),
                    processing_time_ms=processing_time,
                    webhook_source=source_id,
                    request_id=request_id
                )
            
            return {
                'status': 'error',
                'operation': 'create',
                'message': str(e),
                'source_event_id': source_event_id
            }
    
    def handle_event_updated(
        self,
        source_id: str,
        event_data: Dict[str, Any],
        request_id: str = None
    ) -> Dict[str, Any]:
        """
        Handle event update webhook
        
        Args:
            source_id: Source calendar ID
            event_data: Updated event data from webhook
            request_id: Request ID for tracing
            
        Returns:
            Dictionary with operation result
        """
        start_time = datetime.now()
        source_event_id = event_data.get('id')
        
        if not source_event_id:
            logger.error("Event data missing 'id' field")
            return {'status': 'error', 'message': "Missing required field: 'id'"}
        
        logger.info(f"Processing event update: Source={source_id}, EventID={source_event_id}")
        
        try:
            # Get source calendar
            source_calendar = self._get_or_create_source_calendar(source_id)
            
            # Find existing event mapping
            event_mapping = self.db.query(EventMapping).filter_by(
                source_calendar_id=source_calendar.id,
                source_event_id=source_event_id
            ).first()
            
            if not event_mapping:
                logger.warning(
                    f"Event mapping not found for {source_event_id}. "
                    f"Treating as new event."
                )
                return self.handle_event_created(source_id, event_data, request_id)
            
            # Check for conflicts
            should_update, reason = self._resolve_conflict(
                event_mapping, event_data, source_calendar
            )
            
            if not should_update:
                logger.info(f"Skipping update due to conflict resolution: {reason}")
                
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                self._log_sync_operation(
                    operation_type='update',
                    status='skipped',
                    source_calendar=source_calendar,
                    source_event_id=source_event_id,
                    caldav_uid=event_mapping.caldav_uid,
                    event_mapping=event_mapping,
                    details=f"Update skipped: {reason}",
                    processing_time_ms=processing_time,
                    webhook_source=source_id,
                    request_id=request_id
                )
                
                return {
                    'status': 'skipped',
                    'operation': 'update',
                    'reason': reason,
                    'source_event_id': source_event_id
                }
            
            # Parse updated event data
            summary = sanitize_text(event_data.get('subject'))
            start = parse_datetime(event_data.get('start'))
            end = parse_datetime(event_data.get('end'))
            description = sanitize_text(event_data.get('body'))
            location = sanitize_text(event_data.get('location'))
            is_all_day = event_data.get('isAllDay')
            
            # Update event in CalDAV server
            caldav_result = self.caldav.update_event(
                uid=event_mapping.caldav_uid,
                summary=summary,
                start=start,
                end=end,
                description=description,
                location=location,
                is_all_day=is_all_day
            )
            
            # Update event mapping
            if summary:
                event_mapping.event_subject = summary
            if start:
                event_mapping.event_start = start
            if end:
                event_mapping.event_end = end
            if is_all_day is not None:
                event_mapping.is_all_day = is_all_day
            
            event_mapping.source_change_key = event_data.get('changeKey')
            event_mapping.caldav_etag = caldav_result.get('etag')
            event_mapping.last_synced_at = datetime.utcnow()
            event_mapping.last_modified_at = datetime.utcnow()
            event_mapping.sync_status = 'synced'
            event_mapping.sync_attempt_count = 0
            event_mapping.last_error = None
            event_mapping.source_event_data = event_data
            event_mapping.caldav_event_data = {'icalendar': caldav_result['icalendar']}
            
            self.db.commit()
            
            # Log successful operation
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync_operation(
                operation_type='update',
                status='success',
                source_calendar=source_calendar,
                source_event_id=source_event_id,
                caldav_uid=event_mapping.caldav_uid,
                event_mapping=event_mapping,
                details=f"Updated event: {summary or event_mapping.event_subject}",
                processing_time_ms=processing_time,
                webhook_source=source_id,
                request_id=request_id
            )
            
            # Update source calendar sync time
            source_calendar.last_sync_time = datetime.utcnow()
            source_calendar.sync_errors = 0
            self.db.commit()
            
            logger.info(
                f"Event updated successfully: {source_event_id} "
                f"(took {processing_time}ms)"
            )
            
            return {
                'status': 'success',
                'operation': 'update',
                'source_event_id': source_event_id,
                'caldav_uid': event_mapping.caldav_uid,
                'caldav_url': caldav_result['url'],
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Error updating event {source_event_id}: {e}")
            
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if event_mapping:
                event_mapping.sync_attempt_count += 1
                event_mapping.last_error = str(e)
                event_mapping.sync_status = 'error'
                self.db.commit()
            
            if source_calendar:
                source_calendar.sync_errors += 1
                self.db.commit()
                
                self._log_sync_operation(
                    operation_type='update',
                    status='error',
                    source_calendar=source_calendar,
                    source_event_id=source_event_id,
                    caldav_uid=event_mapping.caldav_uid if event_mapping else None,
                    event_mapping=event_mapping,
                    error_message=str(e),
                    processing_time_ms=processing_time,
                    webhook_source=source_id,
                    request_id=request_id
                )
            
            return {
                'status': 'error',
                'operation': 'update',
                'message': str(e),
                'source_event_id': source_event_id
            }
    
    def handle_event_deleted(
        self,
        source_id: str,
        event_data: Dict[str, Any],
        request_id: str = None
    ) -> Dict[str, Any]:
        """
        Handle event deletion webhook
        
        Args:
            source_id: Source calendar ID
            event_data: Deleted event data (must contain 'id')
            request_id: Request ID for tracing
            
        Returns:
            Dictionary with operation result
        """
        start_time = datetime.now()
        source_event_id = event_data.get('id')
        
        if not source_event_id:
            logger.error("Event data missing 'id' field")
            return {'status': 'error', 'message': "Missing required field: 'id'"}
        
        logger.info(f"Processing event deletion: Source={source_id}, EventID={source_event_id}")
        
        try:
            # Get source calendar
            source_calendar = self._get_or_create_source_calendar(source_id)
            
            # Find existing event mapping
            event_mapping = self.db.query(EventMapping).filter_by(
                source_calendar_id=source_calendar.id,
                source_event_id=source_event_id
            ).first()
            
            if not event_mapping:
                logger.warning(f"Event mapping not found for deletion: {source_event_id}")
                
                processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
                self._log_sync_operation(
                    operation_type='delete',
                    status='skipped',
                    source_calendar=source_calendar,
                    source_event_id=source_event_id,
                    details="Event not found in database",
                    processing_time_ms=processing_time,
                    webhook_source=source_id,
                    request_id=request_id
                )
                
                return {
                    'status': 'skipped',
                    'operation': 'delete',
                    'reason': 'Event not found',
                    'source_event_id': source_event_id
                }
            
            # Delete event from CalDAV server
            try:
                self.caldav.delete_event(event_mapping.caldav_uid)
            except Exception as caldav_error:
                logger.warning(f"CalDAV deletion failed (may already be deleted): {caldav_error}")
            
            # Mark event as deleted in database (soft delete)
            event_mapping.mark_deleted()
            self.db.commit()
            
            # Log successful operation
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            self._log_sync_operation(
                operation_type='delete',
                status='success',
                source_calendar=source_calendar,
                source_event_id=source_event_id,
                caldav_uid=event_mapping.caldav_uid,
                event_mapping=event_mapping,
                details=f"Deleted event: {event_mapping.event_subject}",
                processing_time_ms=processing_time,
                webhook_source=source_id,
                request_id=request_id
            )
            
            # Update source calendar sync time
            source_calendar.last_sync_time = datetime.utcnow()
            source_calendar.sync_errors = 0
            self.db.commit()
            
            logger.info(
                f"Event deleted successfully: {source_event_id} "
                f"(took {processing_time}ms)"
            )
            
            return {
                'status': 'success',
                'operation': 'delete',
                'source_event_id': source_event_id,
                'caldav_uid': event_mapping.caldav_uid,
                'processing_time_ms': processing_time
            }
            
        except Exception as e:
            self.db.rollback()
            logger.exception(f"Error deleting event {source_event_id}: {e}")
            
            processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if source_calendar:
                source_calendar.sync_errors += 1
                self.db.commit()
                
                self._log_sync_operation(
                    operation_type='delete',
                    status='error',
                    source_calendar=source_calendar,
                    source_event_id=source_event_id,
                    caldav_uid=event_mapping.caldav_uid if event_mapping else None,
                    event_mapping=event_mapping,
                    error_message=str(e),
                    processing_time_ms=processing_time,
                    webhook_source=source_id,
                    request_id=request_id
                )
            
            return {
                'status': 'error',
                'operation': 'delete',
                'message': str(e),
                'source_event_id': source_event_id
            }
