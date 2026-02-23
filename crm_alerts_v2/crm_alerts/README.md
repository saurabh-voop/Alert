# CRM Daily Stalled Alert System

Automated daily report that monitors Zoho CRM for overdue leads and stalled enquiries, generates multi-sheet Excel reports, and sends personalised email alerts to owners and management — every business day at 9 AM.

---

## Table of Contents

1. [What it does](#what-it-does)
2. [Project structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Configuration](#configuration)
6. [Running manually](#running-manually)
7. [Scheduling (Windows Task Scheduler)](#scheduling-windows-task-scheduler)
8. [Swagger UI / REST API](#swagger-ui--rest-api)
9. [Excel report layout](#excel-report-layout)
10. [Configuration reference](#configuration-reference)
11. [Logs](#logs)
12. [Troubleshooting](#troubleshooting)

---

## What it does

| Step | Action |
|------|--------|
| 1 | Authenticates with Zoho CRM using OAuth 2.0 (refresh token flow) |
| 2 | Fetches all active leads and enquiries via COQL |
| 3 | Applies configurable business-day thresholds (kVA-based for enquiries) |
| 4 | Generates a multi-sheet management Excel report |
| 5 | Sends the report to MD / management via Gmail SMTP |
| 6 | Generates individual Excel files per owner |
| 7 | Emails each owner their personalised report (with management CC) |
| 8 | Logs everything with automatic log rotation (5 MB × 5 backups) |

---

## Project structure

```
crm_alerts/
├── run.py                   ← Entry point — run this manually or via Task Scheduler
├── api.py                   ← FastAPI REST API with Swagger UI
├── setup_scheduler.ps1      ← One-time PowerShell script to register the scheduled task
│
├── config.json              ← Your live config (excluded from git)
├── config.template.json     ← Safe template — copy → config.json and fill in credentials
├── requirements.txt         ← Python dependencies
├── .gitignore               ← Excludes config.json, logs, and generated files
├── README.md                ← This file
│
├── src/
│   ├── __init__.py
│   ├── auth.py              ← Zoho OAuth 2.0 token manager
│   ├── crm.py               ← Zoho CRM API client (COQL + bulk account fetch)
│   ├── analyzer.py          ← Business logic: thresholds, overdue detection
│   ├── email_builder.py     ← HTML email builder (summary + owner alerts)
│   ├── excel_builder.py     ← Multi-sheet Excel report generator
│   └── mailer.py            ← Gmail SMTP sender
│
├── owner_reports/           ← Per-owner Excel files (auto-created, excluded from git)
└── daily_alert.log          ← Rotating log file (excluded from git)
```

---

## Prerequisites

- Python 3.9+
- A Zoho CRM account with API access (India data centre: `zohoapis.in`)
- A Gmail account with **App Password** enabled (not your regular Gmail password)
- Windows 10 / 11 (for Task Scheduler setup)

---

## Installation

### 1. Clone / download the project

```bash
git clone <repo-url>
cd crm_alerts
```

### 2. Create a virtual environment

```bash
python -m venv venv
venv\Scripts\activate        # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Set up configuration

```bash
copy config.template.json config.json
```

Then open `config.json` and replace every `PASTE_YOUR_*` placeholder:

| Placeholder | Where to find it |
|-------------|-----------------|
| `PASTE_YOUR_CLIENT_ID` | Zoho API Console → Client ID |
| `PASTE_YOUR_NEW_CLIENT_SECRET` | Zoho API Console → Client Secret |
| `PASTE_YOUR_REFRESH_TOKEN` | Generated during Zoho OAuth setup |
| `PASTE_YOUR_GMAIL_ADDRESS` | Your Gmail sender address |
| `PASTE_YOUR_APP_PASSWORD` | Gmail → Security → App Passwords (16 chars, no spaces) |

Also update `summary_recipients` and `owner_alert_cc` with real email addresses.

---

## Running manually

### Test mode — no emails sent, Excel saved locally

```bash
python run.py --test
```

### Live mode — sends emails to all recipients

```bash
python run.py
```

### Custom config file

```bash
python run.py --config C:\path\to\other_config.json
```

### Force run on a weekend

```bash
python run.py --force
```

> By default, `run.py` exits immediately on weekends. Use `--force` to override.

---

## Scheduling (Windows Task Scheduler)

Run **once** as Administrator to register the recurring task:

```powershell
# Open PowerShell as Administrator, then:
cd "C:\path\to\crm_alerts"
.\setup_scheduler.ps1
```

This creates a task that runs `run.py` every **Monday–Friday at 9:00 AM**, with output appended to `scheduler_run.log`.

### Customise schedule

```powershell
# Different time
.\setup_scheduler.ps1 -Time "08:30AM"

# Different task name
.\setup_scheduler.ps1 -TaskName "My CRM Alert" -Time "9:00AM"
```

### Manage the task

```powershell
# Run immediately
Start-ScheduledTask -TaskName "CRM Daily Stalled Alert"

# Check last run result
Get-ScheduledTaskInfo -TaskName "CRM Daily Stalled Alert" | Select LastRunTime, LastTaskResult

# View output log
Get-Content "scheduler_run.log" -Tail 50

# Remove the task
Unregister-ScheduledTask -TaskName "CRM Daily Stalled Alert" -Confirm:$false
```

---

## Swagger UI / REST API

Start the API server:

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Then open in your browser:

| URL | Purpose |
|-----|---------|
| `http://localhost:8000/docs` | **Swagger UI** — interactive API explorer |
| `http://localhost:8000/redoc` | ReDoc — alternative documentation |
| `http://localhost:8000/health` | Health check |

### Available endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/api/config` | View active config (credentials redacted) |
| `POST` | `/api/run` | Trigger a manual report run |
| `GET` | `/api/status` | Get status of the last run |
| `GET` | `/api/logs` | Tail the application log |

### Trigger a test run via API

```bash
curl -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d '{"test_mode": true}'
```

### Check run status

```bash
curl http://localhost:8000/api/status
```

---

## Excel report layout

### Management report (`stalled_report_YYYY-MM-DD_HHMMSS.xlsx`)

| Sheet | Contents |
|-------|----------|
| **Owner Summary** | Per-owner rollup: leads overdue, enquiries stalled, total pipeline amount, avg days stalled |
| **Master List** | All stalled enquiries sorted by owner → days stalled |
| **Leads - No Action** | Leads with no CRM activity beyond threshold |
| **Leads - Not Converted** | Leads not converted to enquiry beyond threshold |
| **Yet To Quote** | Stalled enquiries at this stage |
| **Quoted** | Stalled enquiries at this stage |
| **Finalization** | … and so on for each monitored stage |

### Owner report (`owner_reports/{Name}_YYYY-MM-DD_HHMMSS.xlsx`)

| Sheet | Contents |
|-------|----------|
| **Summary** | Count of issues by category |
| **My Leads** | All stalled leads assigned to this owner |
| **Yet To Quote** … | Their stalled enquiries per stage |

**Colour coding in Excel:**

| Colour | Meaning |
|--------|---------|
| Red cell | Stalled ≥ 10 business days past threshold |
| Yellow cell | Stalled ≥ 5 business days past threshold |
| NA | kVA not set — threshold cannot be determined |

---

## Configuration reference

### Lead thresholds

```json
"lead_thresholds": {
    "no_action_days":    1,
    "not_converted_days": 3
}
```

### kVA-based enquiry thresholds

```json
"kva_categories": [
    {
        "label":             "Standard (10-180 kVA)",
        "min_kva":           10,
        "max_kva":           180,
        "yet_to_quote_days": 1,
        "quoted_days":       1,
        "finalization_days": 1
    }
]
```

### Fixed-stage thresholds (kVA-independent)

```json
"fixed_stage_thresholds": {
    "WON":          1,
    "ORDER_BOOKED": 1,
    "HOLD":         7,
    "BUDGETARY":    7,
    "MFC":          2
}
```

### Email settings

```json
"email": {
    "summary_recipients": ["md@company.com", "manager@company.com"],
    "owner_alert_cc":     ["md@company.com"],
    "send_owner_alerts":  true
}
```

Set `"send_owner_alerts": false` to stop individual owner emails.

### Add / remove table columns

Edit `lead_columns` or `enquiry_columns` — the `field` value must match the Zoho CRM API field name exactly:

```json
"lead_columns": [
    {"field": "Full_Name", "label": "Lead Name"},
    {"field": "Company",   "label": "Company"}
]
```

---

## Logs

Logs are written to `daily_alert.log` with automatic rotation (5 MB per file, 5 backups kept).

```
2026-02-23 09:00:01 [INFO] ============================================================
2026-02-23 09:00:01 [INFO] CRM DAILY STALLED ALERT — STARTING
2026-02-23 09:00:01 [INFO] Date:    23-Feb-2026, Monday
2026-02-23 09:00:01 [INFO] Mode:    LIVE
2026-02-23 09:00:02 [INFO] Fetched 50 CRM users.
2026-02-23 09:00:05 [INFO]   Found 250 leads (broad filter)
2026-02-23 09:00:05 [INFO]   After filtering: No action: 12 | Not converted: 35
2026-02-23 09:04:40 [INFO] COMPLETED SUCCESSFULLY
```

Tail via API: `GET /api/logs?lines=100`

Tail via PowerShell: `Get-Content daily_alert.log -Tail 50 -Wait`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Config still has placeholder` | Edit `config.json` and replace every `PASTE_YOUR_*` value |
| `Token refresh failed` | Regenerate the Client Secret in Zoho API Console, update `config.json` |
| `SMTP auth failed` | Enable Gmail 2-Step Verification, generate a new App Password (16 chars, no spaces) |
| Fields show `-` in output | Wrong API field name — verify in Zoho CRM → Setup → Developer Hub → API Names |
| No records returned | Stage values must match CRM exactly (case-sensitive, e.g. `YET_TO_QUOTE`) |
| Email lands in spam | Add the sender address to contacts; prefer a Google Workspace account |
| Task Scheduler not running | Check `scheduler_run.log`; ensure the task's "Start in" directory is correct |
| API server won't start | `pip install -r requirements.txt` to install FastAPI and uvicorn |
