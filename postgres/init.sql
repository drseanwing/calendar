-- ============================================================================
-- Calendar Consolidation System - Database Schema
-- PostgreSQL initialization script
-- Version: 1.0.0
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ============================================================================
-- SOURCE CALENDARS TABLE
-- Stores metadata about each source calendar (M365 tenants, iCloud, etc.)
-- ============================================================================
CREATE TABLE IF NOT EXISTS source_calendars (
    id SERIAL PRIMARY KEY,
    source_id VARCHAR(100) UNIQUE NOT NULL,  -- e.g., 'm365-tenant1', 'm365-tenant2', 'icloud'
    source_type VARCHAR(50) NOT NULL,        -- 'microsoft365', 'icloud', 'google', etc.
    display_name VARCHAR(255),
    description TEXT,
    color VARCHAR(7),                         -- Hex color code for UI
    priority INTEGER DEFAULT 5,               -- For conflict resolution (1-10)
    sync_enabled BOOLEAN DEFAULT true,
    last_sync_time TIMESTAMP WITH TIME ZONE,
    sync_errors INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB                            -- Flexible storage for source-specific data
);

-- Indexes for source_calendars
CREATE INDEX idx_source_calendars_source_id ON source_calendars(source_id);
CREATE INDEX idx_source_calendars_sync_enabled ON source_calendars(sync_enabled);
CREATE INDEX idx_source_calendars_priority ON source_calendars(priority DESC);

-- ============================================================================
-- EVENT MAPPINGS TABLE
-- Core table mapping source events to CalDAV UIDs
-- ============================================================================
CREATE TABLE IF NOT EXISTS event_mappings (
    id SERIAL PRIMARY KEY,
    
    -- Source event information
    source_calendar_id INTEGER REFERENCES source_calendars(id) ON DELETE CASCADE,
    source_event_id VARCHAR(255) NOT NULL,   -- Event ID from source calendar
    source_change_key VARCHAR(255),          -- For optimistic concurrency (M365)
    
    -- CalDAV event information
    caldav_uid VARCHAR(255) NOT NULL,        -- CalDAV UID (RFC 5545)
    caldav_url TEXT,                         -- Full CalDAV URL to the event
    caldav_etag VARCHAR(255),                -- For conflict detection
    
    -- Event metadata
    event_subject VARCHAR(500),
    event_start TIMESTAMP WITH TIME ZONE,
    event_end TIMESTAMP WITH TIME ZONE,
    is_all_day BOOLEAN DEFAULT false,
    is_recurring BOOLEAN DEFAULT false,
    recurrence_pattern JSONB,                -- Store recurrence rules
    
    -- Sync tracking
    sync_status VARCHAR(50) DEFAULT 'synced', -- 'synced', 'pending', 'error', 'deleted'
    last_synced_at TIMESTAMP WITH TIME ZONE,
    last_modified_at TIMESTAMP WITH TIME ZONE,
    sync_attempt_count INTEGER DEFAULT 0,
    last_error TEXT,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP WITH TIME ZONE,     -- Soft delete support
    
    -- Full event data (for debugging and recovery)
    source_event_data JSONB,
    caldav_event_data JSONB,
    
    -- Unique constraint: one source event maps to one CalDAV event
    CONSTRAINT unique_source_event UNIQUE (source_calendar_id, source_event_id)
);

-- Indexes for event_mappings
CREATE INDEX idx_event_mappings_caldav_uid ON event_mappings(caldav_uid);
CREATE INDEX idx_event_mappings_source_event_id ON event_mappings(source_event_id);
CREATE INDEX idx_event_mappings_source_calendar_id ON event_mappings(source_calendar_id);
CREATE INDEX idx_event_mappings_sync_status ON event_mappings(sync_status);
CREATE INDEX idx_event_mappings_event_start ON event_mappings(event_start);
CREATE INDEX idx_event_mappings_event_end ON event_mappings(event_end);
CREATE INDEX idx_event_mappings_deleted_at ON event_mappings(deleted_at) WHERE deleted_at IS NULL;
CREATE INDEX idx_event_mappings_compound ON event_mappings(source_calendar_id, sync_status, deleted_at);

-- GIN index for JSONB columns for efficient querying
CREATE INDEX idx_event_mappings_source_data ON event_mappings USING GIN (source_event_data);
CREATE INDEX idx_event_mappings_recurrence ON event_mappings USING GIN (recurrence_pattern);

-- ============================================================================
-- SYNC HISTORY TABLE
-- Audit log of all sync operations
-- ============================================================================
CREATE TABLE IF NOT EXISTS sync_history (
    id SERIAL PRIMARY KEY,
    event_mapping_id INTEGER REFERENCES event_mappings(id) ON DELETE SET NULL,
    source_calendar_id INTEGER REFERENCES source_calendars(id) ON DELETE SET NULL,
    
    operation_type VARCHAR(50) NOT NULL,     -- 'create', 'update', 'delete'
    status VARCHAR(50) NOT NULL,              -- 'success', 'error', 'skipped'
    
    source_event_id VARCHAR(255),
    caldav_uid VARCHAR(255),
    
    details TEXT,                             -- Human-readable description
    error_message TEXT,
    error_stack TEXT,
    
    -- Performance metrics
    processing_time_ms INTEGER,
    
    -- Request metadata
    webhook_source VARCHAR(100),              -- Which system triggered this
    request_id VARCHAR(255),                  -- For tracing
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB                            -- Additional context
);

-- Indexes for sync_history
CREATE INDEX idx_sync_history_event_mapping ON sync_history(event_mapping_id);
CREATE INDEX idx_sync_history_source_calendar ON sync_history(source_calendar_id);
CREATE INDEX idx_sync_history_operation_type ON sync_history(operation_type);
CREATE INDEX idx_sync_history_status ON sync_history(status);
CREATE INDEX idx_sync_history_created_at ON sync_history(created_at DESC);
CREATE INDEX idx_sync_history_source_event_id ON sync_history(source_event_id);

-- ============================================================================
-- CONFLICT RESOLUTIONS TABLE
-- Track when conflicts occurred and how they were resolved
-- ============================================================================
CREATE TABLE IF NOT EXISTS conflict_resolutions (
    id SERIAL PRIMARY KEY,
    event_mapping_id INTEGER REFERENCES event_mappings(id) ON DELETE CASCADE,
    
    conflict_type VARCHAR(100) NOT NULL,      -- 'concurrent_update', 'deletion_conflict', etc.
    resolution_strategy VARCHAR(100) NOT NULL, -- 'last_write_wins', 'priority_based', 'manual'
    
    -- Conflicting versions
    version_a JSONB,                          -- First version
    version_b JSONB,                          -- Second version
    resolved_version JSONB,                   -- Final version
    
    winning_source_id INTEGER REFERENCES source_calendars(id),
    
    details TEXT,
    resolved_by VARCHAR(100),                 -- 'system', 'user', 'admin'
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

-- Indexes for conflict_resolutions
CREATE INDEX idx_conflict_resolutions_event_mapping ON conflict_resolutions(event_mapping_id);
CREATE INDEX idx_conflict_resolutions_created_at ON conflict_resolutions(created_at DESC);

-- ============================================================================
-- SYSTEM CONFIGURATION TABLE
-- Store system-wide configuration settings
-- ============================================================================
CREATE TABLE IF NOT EXISTS system_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(100) UNIQUE NOT NULL,
    config_value TEXT,
    value_type VARCHAR(50) DEFAULT 'string',  -- 'string', 'number', 'boolean', 'json'
    description TEXT,
    is_sensitive BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Initial configuration values
INSERT INTO system_config (config_key, config_value, value_type, description) VALUES
    ('sync_enabled', 'true', 'boolean', 'Global sync on/off switch'),
    ('conflict_resolution_strategy', 'last_write_wins', 'string', 'Default conflict resolution strategy'),
    ('max_sync_retries', '3', 'number', 'Maximum retry attempts for failed syncs'),
    ('sync_batch_size', '50', 'number', 'Number of events to process per batch'),
    ('history_retention_days', '90', 'number', 'Days to keep sync history'),
    ('enable_event_deduplication', 'true', 'boolean', 'Prevent duplicate events'),
    ('webhook_timeout_seconds', '30', 'number', 'Timeout for webhook processing')
ON CONFLICT (config_key) DO NOTHING;

-- ============================================================================
-- FUNCTIONS AND TRIGGERS
-- ============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for auto-updating updated_at
CREATE TRIGGER update_source_calendars_updated_at 
    BEFORE UPDATE ON source_calendars
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_event_mappings_updated_at 
    BEFORE UPDATE ON event_mappings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_system_config_updated_at 
    BEFORE UPDATE ON system_config
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to clean up old sync history
CREATE OR REPLACE FUNCTION cleanup_old_sync_history()
RETURNS INTEGER AS $$
DECLARE
    retention_days INTEGER;
    deleted_count INTEGER;
BEGIN
    -- Get retention period from config
    SELECT config_value::INTEGER INTO retention_days
    FROM system_config
    WHERE config_key = 'history_retention_days';
    
    IF retention_days IS NULL THEN
        retention_days := 90; -- Default
    END IF;
    
    -- Delete old records
    DELETE FROM sync_history
    WHERE created_at < CURRENT_TIMESTAMP - (retention_days || ' days')::INTERVAL;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: Active event mappings (not deleted)
CREATE OR REPLACE VIEW active_events AS
SELECT 
    em.*,
    sc.source_id,
    sc.display_name as calendar_name,
    sc.priority
FROM event_mappings em
JOIN source_calendars sc ON em.source_calendar_id = sc.id
WHERE em.deleted_at IS NULL
AND em.sync_status != 'deleted';

-- View: Recent sync activity (last 24 hours)
CREATE OR REPLACE VIEW recent_sync_activity AS
SELECT 
    sh.*,
    sc.source_id,
    sc.display_name as calendar_name
FROM sync_history sh
LEFT JOIN source_calendars sc ON sh.source_calendar_id = sc.id
WHERE sh.created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
ORDER BY sh.created_at DESC;

-- View: Sync error summary
CREATE OR REPLACE VIEW sync_error_summary AS
SELECT 
    sc.source_id,
    sc.display_name,
    COUNT(*) as error_count,
    MAX(sh.created_at) as last_error_time,
    string_agg(DISTINCT sh.error_message, '; ') as error_messages
FROM sync_history sh
JOIN source_calendars sc ON sh.source_calendar_id = sc.id
WHERE sh.status = 'error'
AND sh.created_at > CURRENT_TIMESTAMP - INTERVAL '7 days'
GROUP BY sc.source_id, sc.display_name
ORDER BY error_count DESC;

-- ============================================================================
-- INITIAL DATA: Create default source calendars
-- ============================================================================
INSERT INTO source_calendars (source_id, source_type, display_name, description, color, priority) VALUES
    ('m365-tenant1', 'microsoft365', 'M365 Government Tenant', 'Government Microsoft 365 Calendar', '#0078D4', 5),
    ('m365-tenant2', 'microsoft365', 'M365 Primary Tenant', 'Primary Microsoft 365 Calendar', '#106EBE', 5),
    ('icloud', 'icloud', 'iCloud Calendar', 'Apple iCloud Calendar', '#000000', 3)
ON CONFLICT (source_id) DO NOTHING;

-- ============================================================================
-- PERMISSIONS
-- ============================================================================
-- Grant appropriate permissions (adjust as needed for your security requirements)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO calendaruser;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO calendaruser;

-- ============================================================================
-- MAINTENANCE COMMANDS (for reference - run manually or via cron)
-- ============================================================================
-- VACUUM ANALYZE event_mappings;
-- VACUUM ANALYZE sync_history;
-- SELECT cleanup_old_sync_history();
-- REINDEX TABLE event_mappings;

-- ============================================================================
-- END OF INITIALIZATION SCRIPT
-- ============================================================================
