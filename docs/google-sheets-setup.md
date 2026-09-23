# Google Sheets audit log setup

The self-hosted n8n container (no n8n account or subscription needed) writes
leave requests and audit events to a Google Sheet using a Google Cloud
service account. Both are free. This takes about 5 minutes.

The bot works without it: n8n still receives every webhook, and only the
"append to sheet" step fails.

1. **Enable the Sheets API.** Open https://console.cloud.google.com, create or
   select a project, go to **APIs & Services → Library**, search for
   **Google Sheets API** and click **Enable**.
2. **Create a service account.** Go to **IAM & Admin → Service Accounts →
   Create service account**, name it e.g. `hr-bot-sheets`, skip the roles step
   and click **Done**.
3. **Download its key.** Open the service account, go to **Keys → Add key →
   Create new key → JSON**. A `.json` file downloads.
4. **Put the key in the project** at `secrets/google-service-account.json`
   (create the `secrets/` folder). It is gitignored. Never commit it or paste
   its contents anywhere.
5. **Create the spreadsheet** with two tabs, named exactly as below, and these
   headers in row 1:

   | Tab | Row 1 headers |
   |---|---|
   | `Leave Requests` | `timestamp` `username` `days` `reason` |
   | `Audit Log` | `timestamp` `action` `details` `user` `days` `reason` |

6. **Share the sheet** (Share button) with the `client_email` from the JSON
   file, e.g. `hr-bot-sheets@your-project.iam.gserviceaccount.com`, as
   **Editor**.
7. **Set the sheet ID** in `.env`: `GOOGLE_SHEET_ID` is the part of the sheet
   URL between `/d/` and `/edit`.

Then run `docker compose up -d --build` again. n8n picks up the credential at startup.
