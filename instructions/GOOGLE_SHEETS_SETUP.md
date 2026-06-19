# Google Sheets setup for SurveyBot

1. Open [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable **Google Sheets API**
4. Go to **IAM & Admin -> Service Accounts**
5. Create a service account
6. Create a key in JSON format and download it
7. Place JSON credentials file into:
   - `/opt/bots/SurveyBot/credentials/google_sheets.json`
8. Open your target Google Spreadsheet and share access with the service account email (Editor role)
9. Configure `.env`:
   - `GOOGLE_SHEETS_ENABLED=true`
   - `GOOGLE_SHEETS_CREDENTIALS=/opt/bots/SurveyBot/credentials/google_sheets.json`
   - `GOOGLE_SHEETS_SPREADSHEET_ID=<spreadsheet_id>`
10. Restart services:
    - `systemctl restart surveybot`
    - `systemctl restart surveybot-web`
