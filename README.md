# CRM Daily Overdue Alert System

## Project Structure

```
crm_alerts/
├── config.json              ← All settings (EDIT THIS)
├── run.py                   ← Entry point (RUN THIS)
├── requirements.txt         ← Python packages
├── README.md                ← This file
│
└── src/
    ├── __init__.py
    ├── auth.py              ← Zoho OAuth token manager
    ├── crm.py               ← Zoho CRM API calls
    ├── analyzer.py          ← Business logic (thresholds, overdue checks)
    ├── email_builder.py     ← HTML email construction
    └── mailer.py            ← SMTP email sending
```

## What Each File Does

| File | Responsibility |
|------|---------------|
| `config.json` | All editable settings — credentials, thresholds, columns, stages, colors |
| `run.py` | Orchestrates everything — loads config, runs analysis, sends emails |
| `src/auth.py` | Gets a fresh Zoho access token using your refresh token |
| `src/crm.py` | Makes API calls to Zoho CRM — search records, paginate |
| `src/analyzer.py` | Core logic — business day calc, kVA thresholds, overdue detection |
| `src/email_builder.py` | Builds formatted HTML emails (summary + owner alerts) |
| `src/mailer.py` | Sends emails via Gmail SMTP |


## Setup (One-Time)

### Step 1: Install Python package
```
pip install requests
```

### Step 2: Edit config.json
Replace these 5 placeholders:
- `PASTE_YOUR_CLIENT_ID` → Zoho Client ID
- `PASTE_YOUR_NEW_CLIENT_SECRET` → Zoho Client Secret (regenerated)
- `PASTE_YOUR_REFRESH_TOKEN` → Zoho Refresh Token
- `PASTE_YOUR_GMAIL_ADDRESS` → Gmail address for sending
- `PASTE_YOUR_APP_PASSWORD` → 16-character Gmail App Password (no spaces)

Also update:
- `summary_recipients` → actual MD and Manager email addresses


## Running

### Test mode (no emails sent, saves HTML previews)
```
python run.py --test
```
Opens test_summary_email.html and test_owner_*.html in Chrome to preview.

### Live mode (sends actual emails)
```
python run.py
```

### Custom config path
```
python run.py --config /path/to/other_config.json
```

### Check logs
```
cat daily_alert.log
```


## Scheduling (Production)

### Windows Task Scheduler
1. Open Task Scheduler → Create Basic Task
2. Name: "CRM Daily Alert"
3. Trigger: Daily at 9:00 AM
4. Action: Start a program
   - Program: `python`
   - Arguments: `C:\crm_alerts\run.py`
   - Start in: `C:\crm_alerts\`

### Linux Cron
```
crontab -e
0 9 * * 1-5 cd /path/to/crm_alerts && python3 run.py >> cron.log 2>&1
```


## Configuration Guide

### Change email recipients
```json
"summary_recipients": ["md@company.com", "manager@company.com"]
```

### Turn off individual owner alerts
```json
"send_owner_alerts": false
```

### Change lead thresholds
```json
"lead_thresholds": {
    "no_action_days": 1,
    "not_converted_days": 3
}
```

### Change kVA-based enquiry thresholds
```json
{
    "label": "Standard (10-180 kVA)",
    "min_kva": 10,
    "max_kva": 180,
    "yet_to_quote_days": 1,
    "quoted_days": 1,
    "finalization_days": 1
}
```

### Add a new kVA category
Add to the `kva_categories` array:
```json
{
    "label": "Mid-Large (800-1000 kVA)",
    "min_kva": 800,
    "max_kva": 1000,
    "yet_to_quote_days": 4,
    "quoted_days": 4,
    "finalization_days": 4
}
```

### Change fixed-stage thresholds
```json
"fixed_stage_thresholds": {
    "WON": 1,
    "ORDER_BOOKED": 1,
    "HOLD": 7,
    "BUDGETARY": 7,
    "MFC": 2
}
```

### Add/remove table columns
```json
"lead_columns": [
    {"field": "API_Field_Name", "label": "Display Label"},
    ...
]
```

### Fix API field names
If a field shows "-" in emails:
1. Go to Zoho CRM → Setup → Developer Hub → APIs → API Names
2. Click the module (Leads or Deals)
3. Find the correct API name
4. Update it in config.json


## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Config still has placeholder" | Edit config.json and replace ALL `PASTE_YOUR_*` values |
| "Token refresh failed" | Regenerate Client Secret, update config.json |
| "SMTP auth failed" | Check Gmail + App Password. Enable 2-Step Verification. |
| Fields show "-" | Wrong API field name in config.json. Verify in Developer Hub. |
| No records found | Check stage values match CRM exactly (case-sensitive) |
| Email in spam | Add sender to contacts, or use company Google Workspace account |
