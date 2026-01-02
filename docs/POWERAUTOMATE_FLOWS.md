# PowerAutomate Flow Configuration Guide
# Calendar Sync System - M365 Integration
# Version: 1.0.0

This document provides templates and instructions for creating PowerAutomate flows
to sync Microsoft 365 calendar events to your consolidated CalDAV server.

## Prerequisites

- PowerAutomate Premium license (required for HTTP connector)
- Access to M365 calendar
- API Key from your calendar sync system (.env file)
- CalDAV server URL (e.g., https://caldav.yourdomain.com)

## Overview

You need to create THREE flows per M365 tenant:
1. Event Created Flow
2. Event Updated Flow  
3. Event Deleted Flow

Each flow will trigger on the respective calendar event and send a webhook to your
sync middleware.

## Flow 1: Event Created

### Trigger Configuration

**Trigger Type:** "When an event is created (V3)" (Office 365 Outlook)

**Parameters:**
- Calendar id: Select your calendar from the dropdown
- Fetch only with additional restrictions: No
- Time zone: Your timezone (e.g., "E. Australia Standard Time")

### Action Configuration

**Action Type:** HTTP (Premium connector)

**Parameters:**

```
Method: POST

URI: https://caldav.yourdomain.com/api/webhook/event/created

Headers:
  Content-Type: application/json
  X-API-Key: [YOUR_API_KEY_FROM_ENV_FILE]
  X-Calendar-Source: [SOURCE_ID]  # e.g., "m365-tenant1" or "m365-tenant2"

Body (Expression mode):
{
  "id": "@{triggerOutputs()?['body/id']}",
  "subject": "@{triggerOutputs()?['body/subject']}",
  "start": {
    "dateTime": "@{triggerOutputs()?['body/start/dateTime']}",
    "timeZone": "@{triggerOutputs()?['body/start/timeZone']}"
  },
  "end": {
    "dateTime": "@{triggerOutputs()?['body/end/dateTime']}",
    "timeZone": "@{triggerOutputs()?['body/end/timeZone']}"
  },
  "location": "@{triggerOutputs()?['body/location/displayName']}",
  "body": "@{triggerOutputs()?['body/body']}",
  "isAllDay": @{triggerOutputs()?['body/isAllDay']},
  "recurrence": @{triggerOutputs()?['body/recurrence']},
  "changeKey": "@{triggerOutputs()?['body/changeKey']}",
  "categories": @{triggerOutputs()?['body/categories']},
  "importance": "@{triggerOutputs()?['body/importance']}",
  "sensitivity": "@{triggerOutputs()?['body/sensitivity']}",
  "showAs": "@{triggerOutputs()?['body/showAs']}",
  "attendees": @{triggerOutputs()?['body/attendees']}
}
```

**Important Notes:**
- Replace `[YOUR_API_KEY_FROM_ENV_FILE]` with the actual API key from your .env file
- Replace `[SOURCE_ID]` with "m365-tenant1" for first tenant, "m365-tenant2" for second
- The @ symbols before curly braces indicate PowerAutomate expressions
- Boolean and array values don't have quotes (isAllDay, recurrence, attendees)

## Flow 2: Event Updated

### Trigger Configuration

**Trigger Type:** "When an event is updated (V3)" (Office 365 Outlook)

**Parameters:**
- Calendar id: Select your calendar from the dropdown
- Include attachments: No (to reduce payload size)
- Fetch only with additional restrictions: No
- Time zone: Your timezone

### Action Configuration

**Action Type:** HTTP (Premium connector)

**Parameters:**

```
Method: POST

URI: https://caldav.yourdomain.com/api/webhook/event/updated

Headers:
  Content-Type: application/json
  X-API-Key: [YOUR_API_KEY_FROM_ENV_FILE]
  X-Calendar-Source: [SOURCE_ID]

Body (Expression mode):
{
  "id": "@{triggerOutputs()?['body/id']}",
  "subject": "@{triggerOutputs()?['body/subject']}",
  "start": {
    "dateTime": "@{triggerOutputs()?['body/start/dateTime']}",
    "timeZone": "@{triggerOutputs()?['body/start/timeZone']}"
  },
  "end": {
    "dateTime": "@{triggerOutputs()?['body/end/dateTime']}",
    "timeZone": "@{triggerOutputs()?['body/end/timeZone']}"
  },
  "location": "@{triggerOutputs()?['body/location/displayName']}",
  "body": "@{triggerOutputs()?['body/body']}",
  "isAllDay": @{triggerOutputs()?['body/isAllDay']},
  "recurrence": @{triggerOutputs()?['body/recurrence']},
  "changeKey": "@{triggerOutputs()?['body/changeKey']}",
  "categories": @{triggerOutputs()?['body/categories']},
  "importance": "@{triggerOutputs()?['body/importance']}",
  "sensitivity": "@{triggerOutputs()?['body/sensitivity']}",
  "showAs": "@{triggerOutputs()?['body/showAs']}",
  "attendees": @{triggerOutputs()?['body/attendees']}
}
```

## Flow 3: Event Deleted

### Trigger Configuration

**Trigger Type:** "When an event is deleted (V3)" (Office 365 Outlook)

**Parameters:**
- Calendar id: Select your calendar from the dropdown
- Fetch only with additional restrictions: No

### Action Configuration

**Action Type:** HTTP (Premium connector)

**Parameters:**

```
Method: POST

URI: https://caldav.yourdomain.com/api/webhook/event/deleted

Headers:
  Content-Type: application/json
  X-API-Key: [YOUR_API_KEY_FROM_ENV_FILE]
  X-Calendar-Source: [SOURCE_ID]

Body (Expression mode):
{
  "id": "@{triggerOutputs()?['body/id']}"
}
```

**Note:** Deletion webhook only needs the event ID.

## Testing Your Flows

### Test Event Created Flow
1. Create a new calendar event in your M365 calendar
2. Wait 1-2 minutes for the flow to trigger
3. Check flow run history in PowerAutomate
4. Check your middleware logs: `docker-compose logs middleware`
5. Verify event appears in your iOS Calendar app

### Test Event Updated Flow
1. Modify an existing calendar event
2. Wait 1-2 minutes for the flow to trigger
3. Check flow run history
4. Verify changes sync to iOS Calendar app

### Test Event Deleted Flow
1. Delete a calendar event
2. Wait 1-2 minutes for the flow to trigger
3. Check flow run history
4. Verify deletion syncs to iOS Calendar app

## Troubleshooting

### Flow Shows "Succeeded" but No Event in CalDAV

**Check:**
1. Middleware logs: `docker-compose logs -f middleware`
2. Verify X-API-Key matches your .env file
3. Verify X-Calendar-Source is correct ("m365-tenant1" or "m365-tenant2")
4. Check database for event: `SELECT * FROM event_mappings;`

### Flow Shows "Failed"

**Common Issues:**
1. **Authentication Error (401)**
   - X-API-Key is incorrect or missing
   - Check your .env file for the correct API_KEY

2. **Bad Request (400)**
   - X-Calendar-Source header is missing
   - JSON body is malformed
   - Check the Body expression in PowerAutomate

3. **Internal Server Error (500)**
   - Check middleware logs for detailed error
   - Common causes: database connection, CalDAV connection, invalid datetime format

4. **Timeout**
   - Network issue reaching your server
   - Check firewall rules
   - Verify DNS resolves caldav.yourdomain.com
   - Check nginx is running: `docker-compose ps nginx`

### Flow Takes Too Long to Trigger

**Solutions:**
1. PowerAutomate flows can take 1-5 minutes to trigger
2. This is normal M365 behavior, not a system issue
3. For instant sync, you would need to use Microsoft Graph API webhooks (more complex)

## Advanced: Error Handling

You can add error handling to your flows:

1. Add a "Configure run after" step after the HTTP action
2. Set it to run on "has failed" or "has timed out"
3. Add a "Send an email" action to notify you of failures
4. Include the flow run ID and error details

Example email template:
```
Subject: Calendar Sync Error - @{triggerOutputs()?['body/subject']}

Flow: @{workflow().name}
Run ID: @{workflow().run.name}
Event ID: @{triggerOutputs()?['body/id']}
Error: @{body('HTTP')?['message']}

Please check the middleware logs for details.
```

## Monitoring Flow Health

### PowerAutomate Analytics
1. Go to PowerAutomate → My flows
2. Click on each flow
3. Check "28-day run history" analytics
4. Monitor success rate

### Middleware Monitoring
```bash
# Check recent sync operations
curl -H "X-API-Key: YOUR_API_KEY" https://caldav.yourdomain.com/api/stats

# Check sync history
curl -H "X-API-Key: YOUR_API_KEY" https://caldav.yourdomain.com/api/sync-history?limit=50

# Check source calendar status
curl -H "X-API-Key: YOUR_API_KEY" https://caldav.yourdomain.com/api/sources/m365-tenant1
```

## Performance Optimization

### For High-Volume Calendars (100+ events/day)

1. **Increase Flow Concurrency:**
   - Edit flow settings
   - Set "Concurrency Control" to "On"
   - Set degree of parallelism to 25-50

2. **Filter Events:**
   - Add a condition after the trigger
   - Only sync events that meet certain criteria
   - Example: Only sync events in the future

3. **Batch Updates:**
   - Not supported in current version
   - Feature request for future enhancement

## Security Best Practices

1. **API Key Rotation:**
   - Change API_KEY quarterly
   - Update all flows when rotating
   - Test each flow after updating

2. **Network Security:**
   - Use HTTPS only (never HTTP)
   - Keep SSL certificates updated
   - Consider IP whitelisting if possible

3. **Audit Logging:**
   - PowerAutomate tracks all flow runs
   - Middleware logs all operations
   - Review logs monthly for anomalies

## Support Resources

- PowerAutomate Documentation: https://docs.microsoft.com/power-automate/
- Office 365 Connectors: https://docs.microsoft.com/connectors/office365/
- HTTP Connector: https://docs.microsoft.com/connectors/http/
- Middleware API Documentation: See IMPLEMENTATION_GUIDE.md

## Flow Export/Import

To share flows between tenants or team members:

1. Export Flow:
   - Open flow in PowerAutomate
   - Click "..." menu → Export → Package (.zip)
   - Save the package file

2. Import Flow:
   - PowerAutomate → Import → Import Package
   - Upload the .zip file
   - Configure connections for new environment
   - Update X-Calendar-Source and URLs

## Appendix: Flow JSON Schema (for advanced users)

If you want to create flows programmatically using the PowerAutomate API:

```json
{
  "properties": {
    "definition": {
      "triggers": {
        "When_an_event_is_created_(V3)": {
          "type": "ApiConnection",
          "inputs": {
            "host": {
              "connection": {
                "name": "@parameters('$connections')['office365']['connectionId']"
              }
            },
            "method": "get",
            "path": "/v3/calendars/events/onnewevents"
          }
        }
      },
      "actions": {
        "HTTP": {
          "type": "Http",
          "inputs": {
            "method": "POST",
            "uri": "https://caldav.yourdomain.com/api/webhook/event/created",
            "headers": {
              "Content-Type": "application/json",
              "X-API-Key": "@parameters('ApiKey')",
              "X-Calendar-Source": "@parameters('SourceId')"
            },
            "body": "@triggerOutputs()?['body']"
          }
        }
      }
    }
  }
}
```

---

**Need Help?**
- Check logs: `docker-compose logs -f middleware`
- Test API: `curl -H "X-API-Key: YOUR_KEY" https://your-domain/api/health`
- Review docs: IMPLEMENTATION_GUIDE.md
