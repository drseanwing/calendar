# Calendar Consolidation System - Implementation Guide

## Overview
This system consolidates calendars from two Microsoft 365 tenants and iCloud into a single CalDAV server accessible from all your devices.

## Architecture

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   M365 Tenant 1     │     │   M365 Tenant 2     │     │     iCloud          │
│   (Government)      │     │                     │     │                     │
└──────────┬──────────┘     └──────────┬──────────┘     └──────────┬──────────┘
           │                           │                           │
           │ PowerAutomate Webhook     │ PowerAutomate Webhook     │ CalDAV/vdirsyncer
           ▼                           ▼                           ▼
    ┌──────────────────────────────────────────────────────────────────┐
    │                    Nginx Reverse Proxy (SSL)                     │
    │                      https://yourcaldav.domain                   │
    └────────┬────────────────────────────────────┬────────────────────┘
             │                                    │
             │ /api/webhook/*                     │ /caldav/*
             ▼                                    ▼
    ┌────────────────────┐              ┌────────────────────┐
    │  Sync Middleware   │◄────────────►│  Baikal CalDAV     │
    │  (Python Flask)    │   CalDAV     │     Server         │
    └─────────┬──────────┘   Protocol   └────────────────────┘
              │
              │ Event mappings
              ▼
    ┌────────────────────┐
    │    PostgreSQL      │
    │  Event Tracking DB │
    └────────────────────┘
```

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| CalDAV Server | Baikal | RFC 4791 compliant calendar server |
| Sync Middleware | Python 3.11 + Flask | Webhook receiver and calendar sync engine |
| Database | PostgreSQL 15 | Event mapping and metadata storage |
| Reverse Proxy | Nginx | SSL termination and routing |
| Container Orchestration | Docker Compose | Service management |
| M365 Integration | PowerAutomate | Event monitoring and webhooks |
| iCloud Sync | vdirsyncer (optional) | Automated iCloud calendar sync |

## Features

- ✅ **Bi-directional Sync**: Changes from source calendars update consolidated calendar
- ✅ **Event Tracking**: Maintains mapping between source event IDs and CalDAV UIDs
- ✅ **Conflict Resolution**: Last-write-wins with configurable priority
- ✅ **Update Detection**: Handles create, update, and delete operations
- ✅ **Multi-Tenant Support**: Isolated event spaces per source calendar
- ✅ **Extensive Logging**: Detailed file-based logging for debugging
- ✅ **Health Monitoring**: Built-in health check endpoints
- ✅ **Secure**: SSL/TLS with optional authentication

## Prerequisites

- Ubuntu server with Docker and Docker Compose installed
- Portainer (optional, for UI management)
- Domain name with DNS configured (e.g., `caldav.yourdomain.com`)
- SSL certificates (Let's Encrypt recommended)
- PowerAutomate Premium licenses for both M365 tenants
- Network ports 80 and 443 available

## Directory Structure

```
/opt/calendar-sync/
├── docker-compose.yml
├── .env
├── nginx/
│   ├── nginx.conf
│   └── ssl/
│       ├── fullchain.pem
│       └── privkey.pem
├── baikal/
│   ├── config/
│   └── data/
├── middleware/
│   ├── app.py
│   ├── requirements.txt
│   ├── config.py
│   ├── models.py
│   ├── caldav_client.py
│   ├── webhook_handlers.py
│   └── utils.py
├── postgres/
│   ├── init.sql
│   └── data/
└── logs/
    ├── middleware.log
    └── nginx/
```

## Implementation Steps

### Step 1: Initial Server Setup

1. Create project directory:
```bash
sudo mkdir -p /opt/calendar-sync
cd /opt/calendar-sync
```

2. Create subdirectories:
```bash
sudo mkdir -p nginx/ssl baikal/config baikal/data middleware postgres/data logs/nginx
sudo chmod -R 755 /opt/calendar-sync
```

3. Obtain SSL certificates (using certbot):
```bash
sudo certbot certonly --standalone -d caldav.yourdomain.com
sudo cp /etc/letsencrypt/live/caldav.yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/caldav.yourdomain.com/privkey.pem nginx/ssl/
```

### Step 2: Deploy Docker Services

Use the provided `docker-compose.yml` and `.env` files (see separate files).

```bash
# Start services
docker-compose up -d

# Check logs
docker-compose logs -f
```

### Step 3: Configure Baikal

1. Access Baikal admin interface: `https://caldav.yourdomain.com/baikal/admin`
2. Complete initial setup wizard:
   - Set admin password
   - Configure timezone
   - Enable CalDAV
3. Create a user for your consolidated calendar:
   - Username: `consolidated`
   - Password: [secure password]
4. Create a calendar:
   - Name: `All Events`
   - Color: Your preference

### Step 4: Configure Sync Middleware

1. Update `.env` file with your Baikal credentials
2. Initialize database:
```bash
docker-compose exec postgres psql -U calendaruser -d calendardb -f /docker-entrypoint-initdb.d/init.sql
```

3. Test middleware health:
```bash
curl https://caldav.yourdomain.com/api/health
```

### Step 5: Configure PowerAutomate Flows

#### For Each M365 Tenant:

1. **Create Calendar Created Flow**:
   - Trigger: "When an event is created (V3)"
   - Select your target calendar
   - Action: HTTP POST to `https://caldav.yourdomain.com/api/webhook/event/created`
   - Headers:
     - `Content-Type`: `application/json`
     - `X-Calendar-Source`: `m365-tenant1` (or `m365-tenant2`)
     - `X-API-Key`: `[your-api-key-from-.env]`
   - Body:
   ```json
   {
     "id": "@{triggerOutputs()?['body/id']}",
     "subject": "@{triggerOutputs()?['body/subject']}",
     "start": "@{triggerOutputs()?['body/start']}",
     "end": "@{triggerOutputs()?['body/end']}",
     "location": "@{triggerOutputs()?['body/location/displayName']}",
     "body": "@{triggerOutputs()?['body/body/content']}",
     "isAllDay": "@{triggerOutputs()?['body/isAllDay']}",
     "recurrence": "@{triggerOutputs()?['body/recurrence']}",
     "attendees": "@{triggerOutputs()?['body/attendees']}"
   }
   ```

2. **Create Calendar Updated Flow**:
   - Trigger: "When an event is updated (V3)"
   - Action: HTTP POST to `https://caldav.yourdomain.com/api/webhook/event/updated`
   - Same headers and body as above

3. **Create Calendar Deleted Flow**:
   - Trigger: "When an event is deleted (V3)"
   - Action: HTTP POST to `https://caldav.yourdomain.com/api/webhook/event/deleted`
   - Headers: Same as above
   - Body:
   ```json
   {
     "id": "@{triggerOutputs()?['body/id']}"
   }
   ```

### Step 6: Configure iCloud Sync (Optional)

#### Option A: Manual Subscription (Read-Only)
1. Get your iCloud calendar sharing URL
2. Subscribe from consolidated calendar

#### Option B: Automated Sync with vdirsyncer
1. Install vdirsyncer on server:
```bash
docker-compose exec middleware pip install vdirsyncer
```

2. Create vdirsyncer config (see `vdirsyncer_config.txt`)

3. Set up cron job:
```bash
# Run every 15 minutes
*/15 * * * * docker-compose exec -T middleware vdirsyncer sync
```

### Step 7: Connect iOS Devices

1. On iPhone, go to Settings > Calendar > Accounts > Add Account
2. Select "Other" > "Add CalDAV Account"
3. Enter:
   - Server: `caldav.yourdomain.com`
   - Username: `consolidated`
   - Password: [your baikal password]
   - Description: "All Calendars"
4. Toggle on "Calendars"
5. Calendar should appear in Calendar app

### Step 8: Testing

1. **Test Event Creation**:
   - Create event in M365 Tenant 1
   - Wait 1-2 minutes for webhook
   - Verify event appears on iPhone
   - Check logs: `docker-compose logs middleware`

2. **Test Event Update**:
   - Modify event in M365
   - Verify changes sync to iPhone

3. **Test Event Deletion**:
   - Delete event in M365
   - Verify deletion syncs to iPhone

4. **Check Database**:
```bash
docker-compose exec postgres psql -U calendaruser -d calendardb
SELECT * FROM event_mappings;
```

## Monitoring and Maintenance

### Log Files
- Middleware: `/opt/calendar-sync/logs/middleware.log`
- Nginx access: `/opt/calendar-sync/logs/nginx/access.log`
- Nginx error: `/opt/calendar-sync/logs/nginx/error.log`

### Health Checks
```bash
# Middleware health
curl https://caldav.yourdomain.com/api/health

# Database health
docker-compose exec postgres pg_isready -U calendaruser

# Baikal health
curl -I https://caldav.yourdomain.com/baikal/
```

### Backup Strategy
```bash
# Backup PostgreSQL
docker-compose exec postgres pg_dump -U calendaruser calendardb > backup_$(date +%Y%m%d).sql

# Backup Baikal data
tar -czf baikal_backup_$(date +%Y%m%d).tar.gz baikal/

# Automated daily backup (add to cron)
0 2 * * * cd /opt/calendar-sync && ./backup.sh
```

## Troubleshooting

### Events Not Syncing
1. Check PowerAutomate flow run history
2. Review middleware logs for webhook receipts
3. Verify API key matches in PowerAutomate and .env
4. Check network connectivity to server

### Calendar Not Appearing on iOS
1. Verify Baikal user credentials
2. Check caldav.yourdomain.com is accessible
3. Review iOS device logs (Console.app on Mac)
4. Try removing and re-adding account

### Duplicate Events
1. Check event_mappings table for duplicates
2. Review source_event_id uniqueness constraints
3. Clear affected entries and let webhooks recreate

### Database Connection Issues
1. Check PostgreSQL container: `docker-compose ps`
2. Verify credentials in .env
3. Test connection: `docker-compose exec postgres psql -U calendaruser -d calendardb`

## Security Considerations

1. **API Key Protection**: Store API keys securely, rotate regularly
2. **SSL/TLS**: Always use HTTPS, keep certificates updated
3. **Database**: Use strong passwords, limit network exposure
4. **Firewall**: Only expose ports 80 and 443, block all others
5. **Backups**: Encrypt backup files, store off-server
6. **Access Logs**: Regularly review for suspicious activity
7. **Updates**: Keep Docker images updated monthly

## Advanced Configuration

### Custom Event Filtering
Edit `webhook_handlers.py` to add filtering logic:
```python
def should_sync_event(event_data):
    # Example: Only sync events with specific categories
    if event_data.get('categories'):
        return 'Work' in event_data['categories']
    return True
```

### Calendar-Specific Rules
Configure per-source calendar rules in database:
```sql
INSERT INTO source_calendars (source_id, priority, color, sync_enabled) 
VALUES ('m365-tenant1', 1, '#FF5733', true);
```

### Webhook Authentication
Additional security layer in `config.py`:
```python
WEBHOOK_VERIFICATION_TOKEN = "your-secret-token"
```

## Performance Optimization

### For High Volume
- Increase middleware workers in docker-compose.yml
- Enable PostgreSQL connection pooling
- Add Redis for caching (optional)
- Implement event batching for bulk operations

### Resource Limits
Adjust in docker-compose.yml:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

## Future Enhancements

- [ ] Web UI for event mapping management
- [ ] Conflict resolution UI
- [ ] Event filtering and categorization rules
- [ ] Multi-calendar support (separate calendars per source)
- [ ] Calendar sharing and permissions
- [ ] Event attachment handling
- [ ] Recurring event optimization
- [ ] Analytics and sync statistics
- [ ] Mobile app for management

## Support and Resources

- Baikal Documentation: https://sabre.io/baikal/
- CalDAV RFC: https://tools.ietf.org/html/rfc4791
- PowerAutomate Docs: https://docs.microsoft.com/power-automate/
- Python caldav library: https://github.com/python-caldav/caldav

## License

This implementation is provided as-is for personal use. Adjust according to your organization's requirements and compliance needs.

---

**Version**: 1.0.0  
**Last Updated**: 2026-01-02  
**Author**: Claude (for Sean)
