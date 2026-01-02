"""
Database Models
SQLAlchemy ORM models for calendar sync system
Maps to PostgreSQL schema defined in init.sql
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, 
    ForeignKey, Index, UniqueConstraint, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

Base = declarative_base()


class SourceCalendar(Base):
    """
    Represents a source calendar (M365, iCloud, etc.)
    """
    __tablename__ = 'source_calendars'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Identity and type
    source_id = Column(String(100), unique=True, nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # 'microsoft365', 'icloud', etc.
    
    # Display information
    display_name = Column(String(255))
    description = Column(Text)
    color = Column(String(7))  # Hex color code
    
    # Sync configuration
    priority = Column(Integer, default=5, index=True)  # For conflict resolution
    sync_enabled = Column(Boolean, default=True, index=True)
    
    # Sync tracking
    last_sync_time = Column(DateTime(timezone=True))
    sync_errors = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Flexible metadata storage
    metadata = Column(JSON)
    
    # Relationships
    event_mappings = relationship('EventMapping', back_populates='source_calendar', cascade='all, delete-orphan')
    sync_history = relationship('SyncHistory', back_populates='source_calendar')
    
    def __repr__(self) -> str:
        return f"<SourceCalendar(id={self.id}, source_id='{self.source_id}', type='{self.source_type}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'source_id': self.source_id,
            'source_type': self.source_type,
            'display_name': self.display_name,
            'description': self.description,
            'color': self.color,
            'priority': self.priority,
            'sync_enabled': self.sync_enabled,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'sync_errors': self.sync_errors,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata,
        }


class EventMapping(Base):
    """
    Maps source calendar events to CalDAV UIDs
    Core table for maintaining event synchronization
    """
    __tablename__ = 'event_mappings'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Source event information
    source_calendar_id = Column(Integer, ForeignKey('source_calendars.id', ondelete='CASCADE'), nullable=False, index=True)
    source_event_id = Column(String(255), nullable=False, index=True)
    source_change_key = Column(String(255))  # For optimistic concurrency (M365)
    
    # CalDAV event information
    caldav_uid = Column(String(255), nullable=False, index=True)
    caldav_url = Column(Text)
    caldav_etag = Column(String(255))  # For conflict detection
    
    # Event metadata (for quick queries without parsing JSONB)
    event_subject = Column(String(500))
    event_start = Column(DateTime(timezone=True), index=True)
    event_end = Column(DateTime(timezone=True), index=True)
    is_all_day = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_pattern = Column(JSON)
    
    # Sync tracking
    sync_status = Column(String(50), default='synced', index=True)  # 'synced', 'pending', 'error', 'deleted'
    last_synced_at = Column(DateTime(timezone=True))
    last_modified_at = Column(DateTime(timezone=True))
    sync_attempt_count = Column(Integer, default=0)
    last_error = Column(Text)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), index=True)  # Soft delete
    
    # Full event data (for debugging and recovery)
    source_event_data = Column(JSON)
    caldav_event_data = Column(JSON)
    
    # Relationships
    source_calendar = relationship('SourceCalendar', back_populates='event_mappings')
    sync_history = relationship('SyncHistory', back_populates='event_mapping')
    conflict_resolutions = relationship('ConflictResolution', back_populates='event_mapping', cascade='all, delete-orphan')
    
    # Constraints
    __table_args__ = (
        UniqueConstraint('source_calendar_id', 'source_event_id', name='unique_source_event'),
        Index('idx_event_mappings_compound', 'source_calendar_id', 'sync_status', 'deleted_at'),
    )
    
    def __repr__(self) -> str:
        return f"<EventMapping(id={self.id}, source_id='{self.source_event_id}', caldav_uid='{self.caldav_uid}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'source_calendar_id': self.source_calendar_id,
            'source_event_id': self.source_event_id,
            'source_change_key': self.source_change_key,
            'caldav_uid': self.caldav_uid,
            'caldav_url': self.caldav_url,
            'caldav_etag': self.caldav_etag,
            'event_subject': self.event_subject,
            'event_start': self.event_start.isoformat() if self.event_start else None,
            'event_end': self.event_end.isoformat() if self.event_end else None,
            'is_all_day': self.is_all_day,
            'is_recurring': self.is_recurring,
            'recurrence_pattern': self.recurrence_pattern,
            'sync_status': self.sync_status,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'last_modified_at': self.last_modified_at.isoformat() if self.last_modified_at else None,
            'sync_attempt_count': self.sync_attempt_count,
            'last_error': self.last_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'deleted_at': self.deleted_at.isoformat() if self.deleted_at else None,
        }
    
    def is_deleted(self) -> bool:
        """Check if event is soft-deleted"""
        return self.deleted_at is not None
    
    def mark_deleted(self) -> None:
        """Mark event as soft-deleted"""
        self.deleted_at = datetime.utcnow()
        self.sync_status = 'deleted'


class SyncHistory(Base):
    """
    Audit log of all sync operations
    Tracks create, update, and delete operations
    """
    __tablename__ = 'sync_history'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    event_mapping_id = Column(Integer, ForeignKey('event_mappings.id', ondelete='SET NULL'), index=True)
    source_calendar_id = Column(Integer, ForeignKey('source_calendars.id', ondelete='SET NULL'), index=True)
    
    # Operation details
    operation_type = Column(String(50), nullable=False, index=True)  # 'create', 'update', 'delete'
    status = Column(String(50), nullable=False, index=True)  # 'success', 'error', 'skipped'
    
    # Event identifiers
    source_event_id = Column(String(255), index=True)
    caldav_uid = Column(String(255))
    
    # Details and errors
    details = Column(Text)
    error_message = Column(Text)
    error_stack = Column(Text)
    
    # Performance metrics
    processing_time_ms = Column(Integer)
    
    # Request metadata
    webhook_source = Column(String(100))  # Which system triggered this
    request_id = Column(String(255))  # For tracing
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Flexible metadata
    metadata = Column(JSON)
    
    # Relationships
    event_mapping = relationship('EventMapping', back_populates='sync_history')
    source_calendar = relationship('SourceCalendar', back_populates='sync_history')
    
    def __repr__(self) -> str:
        return f"<SyncHistory(id={self.id}, operation='{self.operation_type}', status='{self.status}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'event_mapping_id': self.event_mapping_id,
            'source_calendar_id': self.source_calendar_id,
            'operation_type': self.operation_type,
            'status': self.status,
            'source_event_id': self.source_event_id,
            'caldav_uid': self.caldav_uid,
            'details': self.details,
            'error_message': self.error_message,
            'processing_time_ms': self.processing_time_ms,
            'webhook_source': self.webhook_source,
            'request_id': self.request_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': self.metadata,
        }


class ConflictResolution(Base):
    """
    Tracks conflict occurrences and resolutions
    Used for auditing and improving conflict resolution strategies
    """
    __tablename__ = 'conflict_resolutions'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Foreign keys
    event_mapping_id = Column(Integer, ForeignKey('event_mappings.id', ondelete='CASCADE'), index=True)
    winning_source_id = Column(Integer, ForeignKey('source_calendars.id'))
    
    # Conflict details
    conflict_type = Column(String(100), nullable=False)  # 'concurrent_update', 'deletion_conflict', etc.
    resolution_strategy = Column(String(100), nullable=False)  # 'last_write_wins', 'priority_based', 'manual'
    
    # Conflicting versions (stored as JSONB)
    version_a = Column(JSON)
    version_b = Column(JSON)
    resolved_version = Column(JSON)
    
    # Resolution metadata
    details = Column(Text)
    resolved_by = Column(String(100))  # 'system', 'user', 'admin'
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Flexible metadata
    metadata = Column(JSON)
    
    # Relationships
    event_mapping = relationship('EventMapping', back_populates='conflict_resolutions')
    
    def __repr__(self) -> str:
        return f"<ConflictResolution(id={self.id}, type='{self.conflict_type}', strategy='{self.resolution_strategy}')>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'event_mapping_id': self.event_mapping_id,
            'winning_source_id': self.winning_source_id,
            'conflict_type': self.conflict_type,
            'resolution_strategy': self.resolution_strategy,
            'details': self.details,
            'resolved_by': self.resolved_by,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class SystemConfig(Base):
    """
    System-wide configuration settings
    Allows runtime configuration without code changes
    """
    __tablename__ = 'system_config'
    
    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Configuration
    config_key = Column(String(100), unique=True, nullable=False)
    config_value = Column(Text)
    value_type = Column(String(50), default='string')  # 'string', 'number', 'boolean', 'json'
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self) -> str:
        return f"<SystemConfig(key='{self.config_key}', value='{self.config_value}')>"
    
    def get_value(self) -> Any:
        """Get typed value based on value_type"""
        if self.value_type == 'boolean':
            return self.config_value.lower() == 'true'
        elif self.value_type == 'number':
            try:
                return int(self.config_value)
            except ValueError:
                return float(self.config_value)
        elif self.value_type == 'json':
            import json
            return json.loads(self.config_value)
        else:
            return self.config_value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'config_key': self.config_key,
            'config_value': self.config_value if not self.is_sensitive else '***',
            'value_type': self.value_type,
            'description': self.description,
            'is_sensitive': self.is_sensitive,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
