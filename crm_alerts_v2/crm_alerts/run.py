"""
CRM Daily Overdue Alert — Entry Point
=======================================

Usage:
    python run.py                  → Live run (sends emails)
    python run.py --test           → Test mode (saves HTML files, no emails sent)
    python run.py --config path    → Use a custom config file

Files generated in test mode:
    test_summary_email.html        → Preview of MD summary email
    test_owner_<email>.html        → Preview of each owner's alert email
    Open these in Chrome to see exactly what the emails look like.
"""

import json
import sys
import os
import logging
from datetime import date

# ============================================================================
# SETUP LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("daily_alert.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)

# ============================================================================
# IMPORTS (from src/)
# ============================================================================

from src.auth import ZohoAuth
from src.crm import ZohoCRM
from src.analyzer import find_overdue_leads, find_stalled_enquiries
from src.email_builder import (
    build_summary_html,
    build_owner_html,
    build_all_clear_html
)
from src.mailer import send_email

# ============================================================================
# PARSE ARGUMENTS
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    config_path = "config.json"
    test_mode = False

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--test":
            test_mode = True
        elif args[i] == "--config" and i + 1 < len(args):
            config_path = args[i + 1]
            i += 1
        i += 1

    return config_path, test_mode

# ============================================================================
# LOAD CONFIG
# ============================================================================

def load_config(path: str) -> dict:
    """Load and validate config file."""
    if not os.path.exists(path):
        log.error(f"Config file not found: {path}")
        log.error("Make sure config.json is in the same folder as run.py")
        sys.exit(1)

    with open(path, "r") as f:
        config = json.load(f)

    # Basic validation
    required = ["zoho", "email", "lead_thresholds", "kva_categories"]
    for key in required:
        if key not in config:
            log.error(f"Missing required config section: {key}")
            sys.exit(1)

    # Check for placeholder values
    placeholders = ["PASTE_YOUR_CLIENT_ID", "PASTE_YOUR_NEW_CLIENT_SECRET",
                     "PASTE_YOUR_REFRESH_TOKEN", "PASTE_YOUR_GMAIL_ADDRESS",
                     "PASTE_YOUR_APP_PASSWORD"]

    for ph in placeholders:
        config_str = json.dumps(config)
        if ph in config_str:
            log.error(f"Config still has placeholder: {ph}")
            log.error("Edit config.json and replace all PASTE_YOUR_* values.")
            sys.exit(1)

    return config

# ============================================================================
# SAVE TEST HTML
# ============================================================================

def save_test_html(filename: str, html: str):
    """Save HTML to file for preview in browser."""
    with open(filename, "w", encoding="utf-8") as f:
        f.write(html)
    log.info(f"  Saved: {filename} (open in Chrome to preview)")

# ============================================================================
# MAIN
# ============================================================================

def main():
    config_path, test_mode = parse_args()

    log.info("=" * 60)
    log.info("CRM DAILY OVERDUE ALERT — STARTING")
    log.info(f"Date:    {date.today().strftime('%d-%b-%Y, %A')}")
    log.info(f"Config:  {config_path}")
    log.info(f"Mode:    {'TEST (no emails sent)' if test_mode else 'LIVE'}")
    log.info("=" * 60)

    # --- Load config ---
    config = load_config(config_path)

    # --- Authenticate ---
    log.info("Authenticating with Zoho CRM...")
    auth = ZohoAuth(config)
    crm = ZohoCRM(auth, config)

    # --- Fetch overdue leads ---
    log.info("")
    log.info("--- ANALYZING LEADS ---")
    overdue_no_action, overdue_not_converted, owner_lead_alerts = \
        find_overdue_leads(crm, config)

    # --- Fetch stalled enquiries ---
    log.info("")
    log.info("--- ANALYZING ENQUIRIES ---")
    stage_results, total_enq_count, owner_enq_alerts = \
        find_stalled_enquiries(crm, config)

    # --- Check if anything to report ---
    has_anything = (
        len(overdue_no_action) > 0 or
        len(overdue_not_converted) > 0 or
        total_enq_count > 0
    )

    # --- ALL CLEAR ---
    if not has_anything:
        log.info("")
        log.info("No overdue items found. Sending all-clear email.")
        clear_html = build_all_clear_html()

        if test_mode:
            save_test_html("test_all_clear.html", clear_html)

        subject = f"All Clear — {date.today().strftime('%d-%b-%Y')}"
        for recipient in config["email"]["summary_recipients"]:
            send_email(recipient, subject, clear_html, config, test_mode)

        log.info("Done.")
        return

    # --- BUILD & SEND SUMMARY EMAIL ---
    log.info("")
    log.info("--- BUILDING SUMMARY EMAIL ---")
    summary_html = build_summary_html(
        overdue_no_action, overdue_not_converted,
        stage_results, total_enq_count, config
    )

    if test_mode:
        save_test_html("test_summary_email.html", summary_html)

    subject = f"Daily Overdue Alert Summary — {date.today().strftime('%d-%b-%Y')}"
    for recipient in config["email"]["summary_recipients"]:
        send_email(recipient, subject, summary_html, config, test_mode)

    # --- BUILD & SEND OWNER ALERTS ---
    if config["email"]["send_owner_alerts"]:
        log.info("")
        log.info("--- BUILDING OWNER ALERTS ---")

        all_owners = set(
            list(owner_lead_alerts.keys()) +
            list(owner_enq_alerts.keys())
        )
        log.info(f"Owners with overdue items: {len(all_owners)}")

        for owner_email in all_owners:
            lead_alerts = owner_lead_alerts.get(owner_email, [])
            enq_alerts = owner_enq_alerts.get(owner_email, [])

            owner_html, item_count = build_owner_html(
                owner_email, lead_alerts, enq_alerts, config
            )

            if test_mode:
                safe = owner_email.replace("@", "_at_").replace(".", "_")
                save_test_html(f"test_owner_{safe}.html", owner_html)

            owner_subject = (
                f"ACTION REQUIRED: {item_count} overdue items — "
                f"{date.today().strftime('%d-%b-%Y')}"
            )
            send_email(owner_email, owner_subject, owner_html,
                       config, test_mode)

    # --- DONE ---
    log.info("")
    log.info("=" * 60)
    log.info("COMPLETED SUCCESSFULLY")
    log.info(f"  Leads (no action):     {len(overdue_no_action)}")
    log.info(f"  Leads (not converted): {len(overdue_not_converted)}")
    log.info(f"  Enquiries stalled:       {total_enq_count}")
    log.info(f"  Owner alerts sent:     {len(set(list(owner_lead_alerts.keys()) + list(owner_enq_alerts.keys())))}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
