"""
CRM Daily Stalled Alert — Entry Point
=======================================
Usage:
    python run.py                  → Live run (emails + Excel)
    python run.py --test           → Saves Excel locally, no emails
    python run.py --config path    → Custom config file
"""

import json
import sys
import os
import logging
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

BASE_DIR = Path(__file__).parent

from src.auth import ZohoAuth
from src.crm import ZohoCRM
from src.analyzer import find_overdue_leads, find_stalled_enquiries, resolve_owner
from src.email_builder import build_all_clear_html
from src.excel_builder import build_excel_report, build_owner_excel
from src.mailer import send_email


def _setup_logging():
    log_path = BASE_DIR / "daily_alert.log"
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    rotating = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    rotating.setFormatter(formatter)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(rotating)
    root.addHandler(console)


def load_config(path: str) -> dict:
    if not os.path.exists(path):
        logging.error(f"Config not found: {path}")
        sys.exit(1)

    with open(path) as f:
        config = json.load(f)

    placeholders = [
        "PASTE_YOUR_CLIENT_ID",
        "PASTE_YOUR_NEW_CLIENT_SECRET",
        "PASTE_YOUR_REFRESH_TOKEN",
        "PASTE_YOUR_GMAIL_ADDRESS",
        "PASTE_YOUR_APP_PASSWORD",
    ]
    for ph in placeholders:
        if ph in json.dumps(config):
            logging.error(f"Config still has placeholder: {ph}")
            sys.exit(1)

    return config


def _is_business_day() -> bool:
    return date.today().weekday() < 5  # Monday=0 … Friday=4


def main():
    _setup_logging()
    log = logging.getLogger(__name__)

    config_path = str(BASE_DIR / "config.json")
    test_mode = False

    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--test":
            test_mode = True
        elif arg == "--config" and i + 1 < len(args):
            config_path = args[i + 1]
        elif arg == "--force":
            pass  # allow override of business-day check via --force (no-op, just documented)

    # Skip weekends unless explicitly forced
    if not _is_business_day() and "--force" not in args:
        log.info("Today is a weekend. Skipping run (use --force to override).")
        sys.exit(0)

    log.info("=" * 60)
    log.info("CRM DAILY STALLED ALERT — STARTING")
    log.info(f"Date:    {date.today().strftime('%d-%b-%Y, %A')}")
    log.info(f"Config:  {config_path}")
    log.info(f"Mode:    {'TEST' if test_mode else 'LIVE'}")
    log.info("=" * 60)

    config = load_config(config_path)
    auth = ZohoAuth(config)
    crm = ZohoCRM(auth, config)

    log.info("Fetching CRM users for owner resolution...")
    user_cache = crm.fetch_users()

    log.info("")
    log.info("--- ANALYZING LEADS ---")
    overdue_no_action, overdue_not_converted, owner_lead_alerts = find_overdue_leads(
        crm, config, user_cache
    )

    log.info("")
    log.info("--- ANALYZING ENQUIRIES ---")
    stage_results, total_enq_count, owner_enq_alerts = find_stalled_enquiries(
        crm, config, user_cache
    )

    has_anything = (
        len(overdue_no_action) > 0
        or len(overdue_not_converted) > 0
        or total_enq_count > 0
    )

    if not has_anything:
        log.info("")
        log.info("No stalled items. Sending all-clear.")
        html = build_all_clear_html()
        if test_mode:
            out = BASE_DIR / "test_all_clear.html"
            out.write_text(html, encoding="utf-8")
            log.info(f"Saved: {out}")
        for r in config["email"]["summary_recipients"]:
            send_email(
                r,
                f"All Clear — {date.today().strftime('%d-%b-%Y')}",
                html,
                config,
                test_mode,
            )
        log.info("Done.")
        return

    # Pre-fetch account names in bulk
    log.info("")
    log.info("--- PRE-FETCHING ACCOUNT NAMES ---")
    all_enquiry_records = [
        item["record"]
        for items in stage_results.values()
        for item in items
    ]
    crm.bulk_fetch_accounts(all_enquiry_records)

    # Build Excel report for management
    log.info("")
    log.info("--- BUILDING EXCEL REPORT ---")
    excel_file = build_excel_report(
        overdue_no_action, overdue_not_converted,
        stage_results, config, user_cache, crm
    )

    # Send full report to summary recipients
    log.info("")
    log.info("--- SENDING SUMMARY REPORT ---")
    subject = f"Zoho CRM Stalled Items Report as on — {date.today().strftime('%d-%b-%Y')}"
    summary_body = (
        f"<html><body>"
        f"<p>Please find attached the Stalled Items Report as on {date.today().strftime('%d-%b-%Y')}.</p>"
        f"<p>Leads (no action): <strong>{len(overdue_no_action)}</strong> | "
        f"Leads (not converted): <strong>{len(overdue_not_converted)}</strong> | "
        f"Enquiries stalled: <strong>{total_enq_count}</strong></p>"
        f"</body></html>"
    )
    for r in config["email"]["summary_recipients"]:
        send_email(r, subject, summary_body, config, test_mode, attachment_path=excel_file)

    # Build and send individual owner alerts
    owner_emails_sent = 0
    if config["email"]["send_owner_alerts"]:
        log.info("")
        log.info("--- BUILDING OWNER ALERTS (Excel) ---")
        all_owner_emails = set(list(owner_lead_alerts.keys()) + list(owner_enq_alerts.keys()))
        log.info(f"Owners with stalled items: {len(all_owner_emails)}")

        cc_list = config["email"].get("owner_alert_cc", [])

        for oe in all_owner_emails:
            owner_name = oe
            for uid, udata in user_cache.items():
                if udata.get("email") == oe:
                    owner_name = udata.get("name", oe)
                    break

            la = owner_lead_alerts.get(oe, [])
            ea = owner_enq_alerts.get(oe, [])
            total_items = len(la) + len(ea)

            owner_excel = build_owner_excel(oe, owner_name, la, ea, config, user_cache, crm)

            if owner_excel:
                owner_body = (
                    f"<html><body>"
                    f"<p>Hi {owner_name},</p>"
                    f"<p>You have <strong>{total_items} stalled items in Zoho CRM</strong> that need your attention. "
                    f"Please review the attached report and take action.</p>"
                    f"<p>Report date: {date.today().strftime('%d-%b-%Y')}</p>"
                    f"</body></html>"
                )
                owner_subject = (
                    f"Zoho CRM Stalled Items Report as on {date.today().strftime('%d-%b-%Y')}"
                )
                owner_cc = [cc for cc in cc_list if cc != oe]
                send_email(
                    oe, owner_subject, owner_body, config, test_mode,
                    attachment_path=owner_excel,
                    cc_emails=owner_cc,
                )
                owner_emails_sent += 1

    log.info("")
    log.info("=" * 60)
    log.info("COMPLETED SUCCESSFULLY")
    log.info(f"  Leads (no action):     {len(overdue_no_action)}")
    log.info(f"  Leads (not converted): {len(overdue_not_converted)}")
    log.info(f"  Enquiries stalled:     {total_enq_count}")
    log.info(f"  Owner alerts sent:     {owner_emails_sent}")
    if excel_file:
        log.info(f"  Excel report:          {excel_file}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
