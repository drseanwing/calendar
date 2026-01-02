# Quick Start Guide
# Get your Calendar Consolidation System running in 30 minutes

This guide will get you from zero to a working calendar sync system as quickly as possible.

## Prerequisites Checklist

- [ ] Ubuntu server with Docker and Docker Compose installed
- [ ] Domain name configured (e.g., `caldav.yourdomain.com`)
- [ ] DNS A record pointing to your server
- [ ] Ports 80 and 443 open in firewall
- [ ] PowerAutomate Premium licenses for M365 tenants

## Step 1: Server Setup (5 minutes)

```bash
# SSH into your server
ssh user@your-server-ip

# Create project directory
sudo mkdir -p /opt/calendar-sync
cd /opt/calendar-sync

# Download or copy all files to this directory
# (You should have: docker-compose.yml, .env.template, nginx.conf, etc.)

# Create subdirectories
sudo mkdir -p nginx/ssl baikal/config baikal/data middleware postgres/data logs/nginx
sudo chmod -R 755 /opt/calendar-sync
```

## Step 2: SSL Certificates (5 minutes)

```bash
# Install certbot if not already installed
sudo apt update
sudo apt install certbot -y

# Get SSL certificate
sudo certbot certonly --standalone -d caldav.yourdomain.com

# Copy certificates to nginx directory
sudo cp /etc/letsencrypt/live/caldav.yourdomain.com/fullchain.pem nginx/ssl/
sudo cp /etc/letsencrypt/live/caldav.yourdomain.com/privkey.pem nginx/ssl/
```

## Step 3: Configuration (5 minutes)

```bash
# Copy environment template
cp .env.template .env

# Edit configuration
nano .env

# MINIMUM required changes:
# 1. CALDAV_DOMAIN=caldav.yourdomain.com
# 2. POSTGRES_PASSWORD=<generate strong password>
# 3. CALDAV_PASSWORD=<generate strong password>
# 4. API_KEY=<generate random hex string>

# Generate passwords:
# PostgreSQL password:
openssl rand -base64 32

# CalDAV password:
openssl rand -base64 32

# API Key:
openssl rand -hex 32
```

**Minimal .env file:**
```bash
CALDAV_DOMAIN=caldav.yourdomain.com
POSTGRES_PASSWORD=YOUR_POSTGRES_PASSWORD_HERE
CALDAV_USERNAME=consolidated
CALDAV_PASSWORD=YOUR_CALDAV_PASSWORD_HERE
API_KEY=YOUR_API_KEY_HERE
```

## Step 4: Start Services (2 minutes)

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# Should see all services as "Up":
# - calendar-postgres
# - calendar-baikal  
# - calendar-middleware
# - calendar-nginx

# Check logs
docker-compose logs -f
# Press Ctrl+C to exit logs
```

## Step 5: Configure Baikal (5 minutes)

```bash
# Open browser to: https://caldav.yourdomain.com/baikal/admin

# Initial Setup Wizard:
# 1. Set admin password (save this!)
# 2. Select timezone: Australia/Brisbane (or your timezone)
# 3. Click "Save Changes"

# Create User:
# 1. Click "Users and resources" in left menu
# 2. Click "Add user"
# 3. Username: consolidated
# 4. Password: [same as CALDAV_PASSWORD in .env]
# 5. Display name: All Calendars
# 6. Email: (optional)
# 7. Click "Save"

# Create Calendar:
# 1. Click on "consolidated" user
# 2. Click "Add calendar"
# 3. Display name: All Events
# 4. Description: Consolidated calendar from all sources
# 5. Select a color
# 6. Click "Save"
```

## Step 6: Test System (3 minutes)

```bash
# Test health check
curl https://caldav.yourdomain.com/api/health

# Expected output:
# {
#   "status": "healthy",
#   "components": {
#     "database": "healthy",
#     "caldav": "healthy"
#   }
# }

# Test API authentication
curl -H "X-API-Key: YOUR_API_KEY_HERE" \
     https://caldav.yourdomain.com/api/sources

# Expected output:
# {
#   "status": "success",
#   "count": 3,
#   "sources": [...]
# }
```

## Step 7: Connect iPhone (2 minutes)

```bash
# On iPhone:
# 1. Settings > Calendar > Accounts > Add Account
# 2. Select "Other"
# 3. Select "Add CalDAV Account"
# 4. Enter:
#    - Server: caldav.yourdomain.com
#    - Username: consolidated
#    - Password: [your CALDAV_PASSWORD]
#    - Description: All Calendars
# 5. Toggle "Calendars" on
# 6. Click "Save"
# 7. Calendar should appear in Calendar app
```

## Step 8: PowerAutomate - Tenant 1 (3 minutes per flow)

**Flow 1: Event Created**

1. Go to https://make.powerautomate.com
2. Click "+ Create" > "Automated cloud flow"
3. Name: "Calendar Sync - Created (Tenant 1)"
4. Trigger: Search "Office 365 Outlook" > "When an event is created (V3)"
5. Click "Create"
6. Configure trigger:
   - Calendar id: [Select your calendar]
7. Add step: "HTTP"
8. Configure HTTP:
   - Method: POST
   - URI: `https://caldav.yourdomain.com/api/webhook/event/created`
   - Headers:
     ```
     Content-Type: application/json
     X-API-Key: YOUR_API_KEY_HERE
     X-Calendar-Source: m365-tenant1
     ```
   - Body: (See POWERAUTOMATE_FLOWS.md for complete body)
9. Click "Save"

**Flow 2: Event Updated** - Repeat above with:
- Trigger: "When an event is updated (V3)"
- URI: `/api/webhook/event/updated`

**Flow 3: Event Deleted** - Repeat above with:
- Trigger: "When an event is deleted (V3)"  
- URI: `/api/webhook/event/deleted`
- Body: Only `{"id": "@{triggerOutputs()?['body/id']}"}`

## Step 9: PowerAutomate - Tenant 2 (3 minutes per flow)

Repeat Step 8 but change:
- Flow name to include "(Tenant 2)"
- X-Calendar-Source to: `m365-tenant2`

## Step 10: Test End-to-End (5 minutes)

```bash
# 1. Create event in M365 Tenant 1
#    - Open Outlook
#    - Create new calendar event for tomorrow
#    - Subject: "Test Event 1"
#    - Save

# 2. Wait 1-2 minutes

# 3. Check PowerAutomate flow run history
#    - Go to make.powerautomate.com
#    - Click on flow
#    - Check run history shows "Succeeded"

# 4. Check middleware logs
docker-compose logs middleware | grep "Test Event 1"

# 5. Check iPhone Calendar app
#    - Open Calendar app
#    - Navigate to tomorrow
#    - Should see "Test Event 1"

# 6. Verify in database
docker-compose exec postgres psql -U calendaruser -d calendardb -c \
  "SELECT event_subject, sync_status FROM event_mappings WHERE event_subject LIKE '%Test%';"

# Expected: One row with "Test Event 1" and status "synced"
```

## Troubleshooting Quick Checks

### Events not appearing on iPhone?

```bash
# 1. Check health
curl https://caldav.yourdomain.com/api/health

# 2. Check logs
docker-compose logs -f middleware

# 3. Check database
docker-compose exec postgres psql -U calendaruser -d calendardb -c \
  "SELECT * FROM event_mappings ORDER BY created_at DESC LIMIT 5;"

# 4. Re-add CalDAV account on iPhone
#    Delete account and add again with same credentials
```

### PowerAutomate flow failing?

```bash
# 1. Check flow run details in PowerAutomate
#    - Click on failed run
#    - Expand HTTP action
#    - Check error message

# 2. Common fixes:
#    - Verify X-API-Key matches .env file
#    - Verify X-Calendar-Source is correct
#    - Check URI is correct (https://)
#    - Verify server is accessible from internet
```

### Services not starting?

```bash
# Check individual service logs
docker-compose logs postgres
docker-compose logs baikal
docker-compose logs middleware
docker-compose logs nginx

# Restart services
docker-compose restart

# Rebuild if needed
docker-compose down
docker-compose up -d --build
```

## Next Steps

Once basic system is working:

1. **Add iCloud sync** (optional):
   - See vdirsyncer_config.txt
   - Install vdirsyncer
   - Configure sync

2. **Set up automated backups**:
   ```bash
   # Make backup script executable
   chmod +x backup.sh
   
   # Add to cron (daily at 2 AM)
   crontab -e
   # Add line: 0 2 * * * /opt/calendar-sync/backup.sh
   ```

3. **Configure SSL auto-renewal**:
   ```bash
   # Test renewal
   sudo certbot renew --dry-run
   
   # Add renewal to cron (twice daily)
   sudo crontab -e
   # Add line: 0 0,12 * * * certbot renew --quiet --post-hook "cp /etc/letsencrypt/live/caldav.yourdomain.com/*.pem /opt/calendar-sync/nginx/ssl/ && docker-compose restart nginx"
   ```

4. **Monitor system**:
   ```bash
   # Set up monitoring dashboard
   curl -H "X-API-Key: YOUR_API_KEY" \
        https://caldav.yourdomain.com/api/stats
   ```

5. **Review logs regularly**:
   ```bash
   # Weekly log review
   docker-compose logs --since 7d | grep ERROR
   ```

## Success Checklist

- [ ] All Docker containers running
- [ ] Health check returns "healthy"
- [ ] Baikal admin accessible
- [ ] CalDAV account added to iPhone
- [ ] PowerAutomate flows created for both tenants
- [ ] Test event syncs from M365 to iPhone
- [ ] Test event update syncs
- [ ] Test event deletion syncs
- [ ] Backups configured
- [ ] SSL renewal configured

## Getting Help

If you're stuck:

1. **Check logs first**:
   ```bash
   docker-compose logs -f middleware
   ```

2. **Check database**:
   ```bash
   docker-compose exec postgres psql -U calendaruser -d calendardb
   SELECT * FROM sync_history WHERE status = 'error';
   ```

3. **Verify configuration**:
   ```bash
   cat .env | grep -v PASSWORD | grep -v API_KEY
   ```

4. **Test components individually**:
   ```bash
   # Test PostgreSQL
   docker-compose exec postgres pg_isready
   
   # Test Baikal
   curl https://caldav.yourdomain.com/baikal/
   
   # Test middleware
   curl https://caldav.yourdomain.com/api/health
   ```

## Estimated Total Time: 30-45 minutes

- Server setup: 5 min
- SSL certificates: 5 min  
- Configuration: 5 min
- Start services: 2 min
- Configure Baikal: 5 min
- Test system: 3 min
- Connect iPhone: 2 min
- PowerAutomate Tenant 1: 9 min (3 flows)
- PowerAutomate Tenant 2: 9 min (3 flows)
- End-to-end testing: 5 min

---

**Congratulations!** 🎉

You now have a fully functional multi-tenant calendar consolidation system!

All your M365 calendars will automatically sync to a single calendar on your iPhone and other devices.
