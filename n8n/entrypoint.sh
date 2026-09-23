#!/bin/sh
# Provisions the HR bot's n8n workflows (and the Sheets credential, if a key
# file is mounted) on every start, then runs n8n. Imports upsert by ID.
set -e

KEY_FILE=/secrets/google-service-account.json
if [ -f "$KEY_FILE" ]; then
  node /opt/hr-bot/make-credential.js "$KEY_FILE" /tmp/credential.json
  n8n import:credentials --input=/tmp/credential.json
  rm -f /tmp/credential.json
else
  echo "No $KEY_FILE mounted: webhooks will work, Google Sheets rows will not be written."
fi

n8n import:workflow --separate --input=/opt/hr-bot/workflows
n8n publish:workflow --id=hrLeaveRequest01
n8n publish:workflow --id=hrAuditLogHook01

exec n8n start
