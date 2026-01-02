# Calendar Sync Middleware

Flask-based REST API that receives webhooks from PowerAutomate and synchronizes events to a CalDAV server.

## Directory Structure

```
middleware/
├── app.py                 # Main Flask application with API routes
├── config.py              # Configuration management from environment variables
├── models.py              # SQLAlchemy database models
├── caldav_client.py       # CalDAV server interaction wrapper
├── webhook_handlers.py    # Business logic for processing webhooks
├── utils.py               # Utility functions (datetime parsing, text sanitization, etc.)
├── requirements.txt       # Python dependencies
├── Dockerfile             # Container image definition
└── README.md             # This file
```

## Module Overview

### app.py
Main Flask application that provides:
- REST API endpoints for webhooks (`/api/webhook/*`)
- Management endpoints for monitoring (`/api/sources`, `/api/events`, `/api/stats`)
- Health check endpoint (`/api/health`)
- Request/response middleware for logging and timing
- API key authentication
- Database session management

**Key Routes:**
```
POST /api/webhook/event/created   - Handle event creation
POST /api/webhook/event/updated   - Handle event updates
POST /api/webhook/event/deleted   - Handle event deletions
GET  /api/health                  - Health check
GET  /api/sources                 - List source calendars
GET  /api/events                  - List event mappings
GET  /api/stats                   - System statistics
```

### config.py
Centralized configuration management:
- Loads settings from environment variables
- Validates configuration on startup
- Provides typed access to all settings
- Includes logging configuration
- Handles source calendar priorities

**Usage:**
```python
from config import Config

database_url = Config.DATABASE_URL
caldav_url = Config.CALDAV_URL
priority = Config.get_source_priority('m365-tenant1')
```

### models.py
SQLAlchemy ORM models:
- `SourceCalendar` - Represents source calendars (M365, iCloud)
- `EventMapping` - Maps source events to CalDAV UIDs
- `SyncHistory` - Audit log of sync operations
- `ConflictResolution` - Tracks conflict resolution
- `SystemConfig` - Runtime configuration storage

**Usage:**
```python
from models import SourceCalendar, EventMapping

# Query examples
source = db.query(SourceCalendar).filter_by(source_id='m365-tenant1').first()
events = db.query(EventMapping).filter_by(sync_status='error').all()
```

### caldav_client.py
CalDAV server interaction wrapper:
- Create, update, delete calendar events
- Automatic retry logic with exponential backoff
- Connection pooling
- iCalendar format handling
- Timezone-aware datetime processing

**Usage:**
```python
from caldav_client import CalDAVClient

client = CalDAVClient()
client.create_event(
    uid='unique-id',
    summary='Meeting',
    start=datetime.now(),
    end=datetime.now() + timedelta(hours=1)
)
```

### webhook_handlers.py
Core business logic for webhook processing:
- `WebhookHandler` class with methods for create/update/delete
- Event deduplication
- Conflict resolution
- Sync history logging
- Error handling with graceful degradation

**Features:**
- Automatic retry on transient failures
- Conflict resolution strategies (last_write_wins, priority_based, manual)
- Comprehensive error logging
- Performance tracking

**Usage:**
```python
from webhook_handlers import WebhookHandler

handler = WebhookHandler(db_session, caldav_client)
result = handler.handle_event_created('m365-tenant1', event_data, request_id)
```

### utils.py
Common utility functions:
- `parse_datetime()` - Parse various datetime formats (M365, ISO, etc.)
- `generate_caldav_uid()` - Generate deterministic CalDAV UIDs
- `sanitize_text()` - Clean and sanitize text input
- `validate_api_key()` - API key validation
- `format_duration()` - Human-readable duration formatting
- Various helper functions for timezone handling, text processing, etc.

**Usage:**
```python
from utils import parse_datetime, generate_caldav_uid

dt = parse_datetime({"dateTime": "2024-01-15T10:30:00", "timeZone": "Pacific Standard Time"})
uid = generate_caldav_uid("m365-tenant1", "AAMkAGI2...")
```

## Development

### Local Development Setup

1. **Install dependencies:**
```bash
cd middleware
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Set up environment variables:**
```bash
cp ../.env.template .env
# Edit .env with your configuration
```

3. **Run locally:**
```bash
export FLASK_ENV=development
export FLASK_DEBUG=true
python app.py
```

Server will start on http://localhost:5000

### Testing API Endpoints

**Test webhook:**
```bash
curl -X POST http://localhost:5000/api/webhook/event/created \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-api-key" \
  -H "X-Calendar-Source: m365-tenant1" \
  -d '{
    "id": "test-event-123",
    "subject": "Test Event",
    "start": {"dateTime": "2024-01-15T10:00:00", "timeZone": "UTC"},
    "end": {"dateTime": "2024-01-15T11:00:00", "timeZone": "UTC"}
  }'
```

**Test health check:**
```bash
curl http://localhost:5000/api/health
```

**Test management APIs:**
```bash
# List sources
curl -H "X-API-Key: your-api-key" http://localhost:5000/api/sources

# Get statistics
curl -H "X-API-Key: your-api-key" http://localhost:5000/api/stats

# List events
curl -H "X-API-Key: your-api-key" http://localhost:5000/api/events?limit=10
```

### Debugging

**Enable debug logging:**
```bash
export LOG_LEVEL=DEBUG
python app.py
```

**Check logs:**
```bash
# In Docker
docker-compose logs -f middleware

# Local development
tail -f /app/logs/middleware.log
```

**Database inspection:**
```bash
# Connect to database
docker-compose exec postgres psql -U calendaruser -d calendardb

# Useful queries
SELECT * FROM source_calendars;
SELECT * FROM event_mappings WHERE sync_status = 'error';
SELECT * FROM sync_history ORDER BY created_at DESC LIMIT 10;
```

## Environment Variables

See `.env.template` for all available environment variables. Key variables:

**Required:**
- `DATABASE_URL` - PostgreSQL connection string
- `CALDAV_URL` - CalDAV server URL
- `CALDAV_USERNAME` - CalDAV username
- `CALDAV_PASSWORD` - CalDAV password
- `API_KEY` - API key for webhook authentication

**Optional:**
- `LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- `SYNC_BATCH_SIZE` - Number of events to process per batch
- `CONFLICT_RESOLUTION` - Conflict resolution strategy
- `SOURCE_PRIORITY_*` - Priority values for each source

## Adding New Features

### Adding a New Webhook Endpoint

1. **Add route in app.py:**
```python
@app.route('/api/webhook/event/custom', methods=['POST'])
@require_api_key
def webhook_custom_action():
    source_id = request.headers.get('X-Calendar-Source')
    event_data = request.get_json()
    
    handler = WebhookHandler(g.db, caldav_client)
    result = handler.handle_custom_action(source_id, event_data, g.request_id)
    
    return jsonify(result), 200
```

2. **Add handler in webhook_handlers.py:**
```python
def handle_custom_action(self, source_id, event_data, request_id=None):
    # Your implementation
    pass
```

### Adding a New Data Model

1. **Define model in models.py:**
```python
class CustomModel(Base):
    __tablename__ = 'custom_table'
    
    id = Column(Integer, primary_key=True)
    # ... other columns
```

2. **Create migration:**
```sql
-- Add to postgres/init.sql or create separate migration
CREATE TABLE custom_table (
    id SERIAL PRIMARY KEY,
    -- ... other columns
);
```

3. **Update database:**
```bash
docker-compose down
docker-compose up -d postgres
# Database will auto-create tables from init.sql
```

## Performance Optimization

### Database Connection Pooling

Configured in config.py:
```python
SQLALCHEMY_POOL_SIZE = 10
SQLALCHEMY_MAX_OVERFLOW = 20
SQLALCHEMY_POOL_RECYCLE = 3600
```

### Gunicorn Workers

Configured in Dockerfile:
```bash
CMD ["gunicorn", "--workers", "4", "--threads", "2", ...]
```

Adjust based on your server resources:
- Workers = (2 × CPU cores) + 1
- Threads = 2-4 per worker

### CalDAV Connection Retry

Configured in caldav_client.py:
```python
CALDAV_RETRY_ATTEMPTS = 3
CALDAV_RETRY_DELAY = 2  # seconds
```

## Security

### API Key Authentication

All webhook endpoints require `X-API-Key` header:
```python
@app.route('/api/webhook/*')
@require_api_key  # Decorator enforces API key check
def webhook_handler():
    pass
```

### SQL Injection Prevention

Using SQLAlchemy ORM prevents SQL injection:
```python
# Safe (parameterized)
db.query(EventMapping).filter_by(source_event_id=user_input).first()

# Unsafe (never do this)
db.execute(f"SELECT * FROM events WHERE id = '{user_input}'")
```

### Input Validation

All user input is sanitized:
```python
from utils import sanitize_text

safe_subject = sanitize_text(event_data.get('subject'))
```

## Logging

### Log Levels

- `DEBUG` - Detailed information for diagnosing problems
- `INFO` - General informational messages
- `WARNING` - Warning messages (still functioning)
- `ERROR` - Error messages (functionality affected)
- `CRITICAL` - Critical errors (application may crash)

### Log Format

JSON format for structured logging:
```json
{
  "asctime": "2024-01-15 10:30:45",
  "name": "app",
  "levelname": "INFO",
  "message": "Event created successfully: test-event-123",
  "filename": "webhook_handlers.py",
  "lineno": 234
}
```

### Log Rotation

Automatic log rotation configured in config.py:
```python
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5  # Keep 5 old log files
```

## Common Issues

### "Database connection failed"
- Check DATABASE_URL is correct
- Verify postgres container is running: `docker-compose ps postgres`
- Check database credentials in .env

### "CalDAV server unreachable"
- Check CALDAV_URL is correct
- Verify baikal container is running: `docker-compose ps baikal`
- Check caldav credentials in .env

### "Event already exists"
- This is normal for duplicate webhooks
- System automatically treats as update
- Check event_mappings table for existing entry

### "Unauthorized (401)"
- API key is incorrect
- Check X-API-Key header matches API_KEY in .env
- Ensure no extra spaces in API key

## Testing

### Unit Tests (TODO)
```bash
pytest tests/
```

### Integration Tests
```bash
# Start test environment
docker-compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## Contributing

When adding features:

1. **Follow existing patterns** - Look at similar code first
2. **Add logging** - Include INFO logs for important operations, DEBUG for details
3. **Handle errors** - Use try/except with proper error messages
4. **Document** - Add docstrings to functions and classes
5. **Test** - Manually test with curl before submitting

## Support

For issues or questions:
1. Check logs: `docker-compose logs -f middleware`
2. Check database: `SELECT * FROM sync_history WHERE status = 'error';`
3. Review configuration: Verify all environment variables are set
4. Test connectivity: Use health check endpoint

## Version History

- **1.0.0** (2024-01-15) - Initial release
  - Basic webhook handling
  - CalDAV sync
  - Conflict resolution
  - Comprehensive logging
