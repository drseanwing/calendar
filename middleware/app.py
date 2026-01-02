"""
Calendar Sync Middleware - Main Flask Application
Provides REST API endpoints for receiving webhooks and managing calendar sync
Handles authentication, logging, database connections, and request routing
"""

import logging
import logging.config
from functools import wraps
from typing import Tuple

from flask import Flask, request, jsonify, g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import NullPool

from config import Config
from models import Base, SourceCalendar, EventMapping, SyncHistory, SystemConfig
from caldav_client import CalDAVClient
from webhook_handlers import WebhookHandler
from utils import validate_api_key, generate_request_id, format_duration

# ============================================================================
# Logging Configuration
# ============================================================================
logging.config.dictConfig(Config.get_logging_config())
logger = logging.getLogger(__name__)

# ============================================================================
# Flask Application Setup
# ============================================================================
app = Flask(__name__)
app.config.from_object(Config)

logger.info("=" * 80)
logger.info("Calendar Sync Middleware Starting")
logger.info("=" * 80)
logger.info(f"Environment: {Config.FLASK_ENV}")
logger.info(f"Database: {Config.DATABASE_URL.split('@')[1] if '@' in Config.DATABASE_URL else 'local'}")
logger.info(f"CalDAV Server: {Config.CALDAV_URL}")
logger.info(f"Log Level: {Config.LOG_LEVEL}")
logger.info(f"Timezone: {Config.TIMEZONE}")
logger.info("=" * 80)

# ============================================================================
# Database Setup
# ============================================================================
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    pool_size=Config.SQLALCHEMY_POOL_SIZE,
    max_overflow=Config.SQLALCHEMY_MAX_OVERFLOW,
    pool_recycle=Config.SQLALCHEMY_POOL_RECYCLE,
    echo=Config.SQLALCHEMY_ECHO,
    poolclass=NullPool if Config.FLASK_DEBUG else None
)

SessionLocal = scoped_session(sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
))

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)
logger.info("Database tables initialized")

# ============================================================================
# CalDAV Client Setup
# ============================================================================
caldav_client = CalDAVClient()
logger.info("CalDAV client initialized")

# ============================================================================
# Request/Response Middleware
# ============================================================================

@app.before_request
def before_request():
    """
    Execute before each request
    Sets up database session and request tracking
    """
    # Generate request ID for tracing
    g.request_id = generate_request_id()
    
    # Create database session
    g.db = SessionLocal()
    
    # Log incoming request
    logger.info(
        f"[{g.request_id}] {request.method} {request.path} "
        f"from {request.remote_addr}"
    )
    
    # Store request start time for performance tracking
    import time
    g.request_start_time = time.time()


@app.after_request
def after_request(response):
    """
    Execute after each request
    Logs response and adds headers
    """
    import time
    
    # Calculate request processing time
    if hasattr(g, 'request_start_time'):
        duration_ms = int((time.time() - g.request_start_time) * 1000)
        response.headers['X-Processing-Time'] = str(duration_ms)
        
        logger.info(
            f"[{g.request_id}] Response: {response.status_code} "
            f"(took {format_duration(duration_ms)})"
        )
    
    # Add request ID header
    if hasattr(g, 'request_id'):
        response.headers['X-Request-ID'] = g.request_id
    
    # Add CORS headers if needed
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, X-API-Key, X-Calendar-Source'
    
    return response


@app.teardown_appcontext
def shutdown_session(exception=None):
    """
    Close database session after request
    """
    if hasattr(g, 'db'):
        g.db.close()
        SessionLocal.remove()


# ============================================================================
# Authentication Decorator
# ============================================================================

def require_api_key(f):
    """
    Decorator to require API key authentication
    Checks X-API-Key header against configured API keys
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not validate_api_key(api_key):
            logger.warning(
                f"[{g.request_id}] Unauthorized request: Invalid or missing API key"
            )
            return jsonify({
                'status': 'error',
                'message': 'Invalid or missing API key'
            }), 401
        
        return f(*args, **kwargs)
    
    return decorated_function


# ============================================================================
# Health Check Endpoint
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """
    Health check endpoint
    Returns system status and component health
    """
    health_status = {
        'status': 'healthy',
        'components': {}
    }
    
    # Check database
    try:
        g.db.execute('SELECT 1')
        health_status['components']['database'] = 'healthy'
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status['components']['database'] = 'unhealthy'
        health_status['status'] = 'degraded'
    
    # Check CalDAV server
    try:
        if caldav_client.health_check():
            health_status['components']['caldav'] = 'healthy'
        else:
            health_status['components']['caldav'] = 'unhealthy'
            health_status['status'] = 'degraded'
    except Exception as e:
        logger.error(f"CalDAV health check failed: {e}")
        health_status['components']['caldav'] = 'unhealthy'
        health_status['status'] = 'degraded'
    
    # Return appropriate status code
    status_code = 200 if health_status['status'] == 'healthy' else 503
    
    return jsonify(health_status), status_code


# ============================================================================
# Webhook Endpoints
# ============================================================================

@app.route('/api/webhook/event/created', methods=['POST'])
@require_api_key
def webhook_event_created():
    """
    Handle event creation webhook from PowerAutomate
    
    Request Headers:
        X-API-Key: API key for authentication
        X-Calendar-Source: Source calendar ID (e.g., 'm365-tenant1')
    
    Request Body:
        JSON object with event data
    
    Returns:
        JSON response with operation result
    """
    source_id = request.headers.get('X-Calendar-Source')
    
    if not source_id:
        logger.warning(f"[{g.request_id}] Missing X-Calendar-Source header")
        return jsonify({
            'status': 'error',
            'message': 'Missing X-Calendar-Source header'
        }), 400
    
    event_data = request.get_json()
    
    if not event_data:
        logger.warning(f"[{g.request_id}] Missing or invalid JSON body")
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid JSON body'
        }), 400
    
    logger.info(f"[{g.request_id}] Event creation webhook from {source_id}")
    
    # Process webhook
    handler = WebhookHandler(g.db, caldav_client)
    result = handler.handle_event_created(source_id, event_data, g.request_id)
    
    # Return appropriate status code
    status_code = 200 if result['status'] == 'success' else 500
    
    return jsonify(result), status_code


@app.route('/api/webhook/event/updated', methods=['POST'])
@require_api_key
def webhook_event_updated():
    """
    Handle event update webhook from PowerAutomate
    
    Request Headers:
        X-API-Key: API key for authentication
        X-Calendar-Source: Source calendar ID
    
    Request Body:
        JSON object with updated event data
    
    Returns:
        JSON response with operation result
    """
    source_id = request.headers.get('X-Calendar-Source')
    
    if not source_id:
        logger.warning(f"[{g.request_id}] Missing X-Calendar-Source header")
        return jsonify({
            'status': 'error',
            'message': 'Missing X-Calendar-Source header'
        }), 400
    
    event_data = request.get_json()
    
    if not event_data:
        logger.warning(f"[{g.request_id}] Missing or invalid JSON body")
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid JSON body'
        }), 400
    
    logger.info(f"[{g.request_id}] Event update webhook from {source_id}")
    
    # Process webhook
    handler = WebhookHandler(g.db, caldav_client)
    result = handler.handle_event_updated(source_id, event_data, g.request_id)
    
    # Return appropriate status code
    if result['status'] == 'success':
        status_code = 200
    elif result['status'] == 'skipped':
        status_code = 200  # Still successful, just skipped
    else:
        status_code = 500
    
    return jsonify(result), status_code


@app.route('/api/webhook/event/deleted', methods=['POST'])
@require_api_key
def webhook_event_deleted():
    """
    Handle event deletion webhook from PowerAutomate
    
    Request Headers:
        X-API-Key: API key for authentication
        X-Calendar-Source: Source calendar ID
    
    Request Body:
        JSON object with event ID
    
    Returns:
        JSON response with operation result
    """
    source_id = request.headers.get('X-Calendar-Source')
    
    if not source_id:
        logger.warning(f"[{g.request_id}] Missing X-Calendar-Source header")
        return jsonify({
            'status': 'error',
            'message': 'Missing X-Calendar-Source header'
        }), 400
    
    event_data = request.get_json()
    
    if not event_data:
        logger.warning(f"[{g.request_id}] Missing or invalid JSON body")
        return jsonify({
            'status': 'error',
            'message': 'Missing or invalid JSON body'
        }), 400
    
    logger.info(f"[{g.request_id}] Event deletion webhook from {source_id}")
    
    # Process webhook
    handler = WebhookHandler(g.db, caldav_client)
    result = handler.handle_event_deleted(source_id, event_data, g.request_id)
    
    # Return appropriate status code
    if result['status'] == 'success':
        status_code = 200
    elif result['status'] == 'skipped':
        status_code = 200
    else:
        status_code = 500
    
    return jsonify(result), status_code


# ============================================================================
# Management API Endpoints (Optional - for monitoring and debugging)
# ============================================================================

@app.route('/api/sources', methods=['GET'])
@require_api_key
def list_sources():
    """
    List all source calendars
    
    Returns:
        JSON array of source calendars
    """
    sources = g.db.query(SourceCalendar).all()
    
    return jsonify({
        'status': 'success',
        'count': len(sources),
        'sources': [source.to_dict() for source in sources]
    })


@app.route('/api/sources/<source_id>', methods=['GET'])
@require_api_key
def get_source(source_id: str):
    """
    Get details for a specific source calendar
    
    Args:
        source_id: Source calendar ID
    
    Returns:
        JSON object with source calendar details
    """
    source = g.db.query(SourceCalendar).filter_by(source_id=source_id).first()
    
    if not source:
        return jsonify({
            'status': 'error',
            'message': 'Source calendar not found'
        }), 404
    
    # Get recent sync history
    recent_syncs = g.db.query(SyncHistory)\
        .filter_by(source_calendar_id=source.id)\
        .order_by(SyncHistory.created_at.desc())\
        .limit(10)\
        .all()
    
    return jsonify({
        'status': 'success',
        'source': source.to_dict(),
        'recent_syncs': [sync.to_dict() for sync in recent_syncs]
    })


@app.route('/api/events', methods=['GET'])
@require_api_key
def list_events():
    """
    List event mappings with optional filtering
    
    Query Parameters:
        source_id: Filter by source calendar ID
        sync_status: Filter by sync status
        limit: Maximum number of results (default: 100)
    
    Returns:
        JSON array of event mappings
    """
    query = g.db.query(EventMapping).filter(EventMapping.deleted_at.is_(None))
    
    # Apply filters
    source_id = request.args.get('source_id')
    if source_id:
        source = g.db.query(SourceCalendar).filter_by(source_id=source_id).first()
        if source:
            query = query.filter_by(source_calendar_id=source.id)
    
    sync_status = request.args.get('sync_status')
    if sync_status:
        query = query.filter_by(sync_status=sync_status)
    
    # Apply limit
    limit = min(int(request.args.get('limit', 100)), 1000)
    events = query.order_by(EventMapping.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'status': 'success',
        'count': len(events),
        'events': [event.to_dict() for event in events]
    })


@app.route('/api/sync-history', methods=['GET'])
@require_api_key
def list_sync_history():
    """
    List sync history with optional filtering
    
    Query Parameters:
        source_id: Filter by source calendar ID
        operation_type: Filter by operation type
        status: Filter by status
        limit: Maximum number of results (default: 100)
    
    Returns:
        JSON array of sync history entries
    """
    query = g.db.query(SyncHistory)
    
    # Apply filters
    source_id = request.args.get('source_id')
    if source_id:
        source = g.db.query(SourceCalendar).filter_by(source_id=source_id).first()
        if source:
            query = query.filter_by(source_calendar_id=source.id)
    
    operation_type = request.args.get('operation_type')
    if operation_type:
        query = query.filter_by(operation_type=operation_type)
    
    status = request.args.get('status')
    if status:
        query = query.filter_by(status=status)
    
    # Apply limit
    limit = min(int(request.args.get('limit', 100)), 1000)
    history = query.order_by(SyncHistory.created_at.desc()).limit(limit).all()
    
    return jsonify({
        'status': 'success',
        'count': len(history),
        'history': [entry.to_dict() for entry in history]
    })


@app.route('/api/stats', methods=['GET'])
@require_api_key
def get_stats():
    """
    Get system statistics
    
    Returns:
        JSON object with various statistics
    """
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    stats = {}
    
    # Total events
    stats['total_events'] = g.db.query(EventMapping)\
        .filter(EventMapping.deleted_at.is_(None))\
        .count()
    
    # Events by status
    status_counts = g.db.query(
        EventMapping.sync_status,
        func.count(EventMapping.id)
    ).filter(EventMapping.deleted_at.is_(None))\
     .group_by(EventMapping.sync_status)\
     .all()
    
    stats['events_by_status'] = {status: count for status, count in status_counts}
    
    # Sync operations in last 24 hours
    yesterday = datetime.utcnow() - timedelta(days=1)
    recent_syncs = g.db.query(
        SyncHistory.operation_type,
        SyncHistory.status,
        func.count(SyncHistory.id)
    ).filter(SyncHistory.created_at >= yesterday)\
     .group_by(SyncHistory.operation_type, SyncHistory.status)\
     .all()
    
    stats['recent_sync_operations'] = [
        {'operation': op, 'status': status, 'count': count}
        for op, status, count in recent_syncs
    ]
    
    # Source calendar stats
    source_stats = []
    sources = g.db.query(SourceCalendar).all()
    for source in sources:
        event_count = g.db.query(EventMapping)\
            .filter_by(source_calendar_id=source.id)\
            .filter(EventMapping.deleted_at.is_(None))\
            .count()
        
        source_stats.append({
            'source_id': source.source_id,
            'display_name': source.display_name,
            'event_count': event_count,
            'last_sync': source.last_sync_time.isoformat() if source.last_sync_time else None,
            'sync_errors': source.sync_errors
        })
    
    stats['sources'] = source_stats
    
    return jsonify({
        'status': 'success',
        'stats': stats
    })


# ============================================================================
# Error Handlers
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    logger.exception("Internal server error")
    g.db.rollback()
    
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == '__main__':
    # Development server (use gunicorn in production)
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=Config.FLASK_DEBUG
    )
