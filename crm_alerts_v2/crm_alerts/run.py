"""
CRM Daily Stalled Alert — Entry Point
=======================================
Usage:
    python run.py                  → Live run (emails + Excel)
    python run.py --test           → Saves HTML + Excel locally, no emails
    python run.py --config path    → Custom config file
"""

import json, sys, os, logging
from datetime import date

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("daily_alert.log", encoding="utf-8")]
)
log = logging.getLogger(__name__)

from src.auth import ZohoAuth
from src.crm import ZohoCRM
from src.analyzer import find_overdue_leads, find_stalled_enquiries
from src.email_builder import build_summary_html, build_owner_html, build_all_clear_html
from src.excel_builder import build_excel_report
from src.mailer import send_email


def load_config(path):
    if not os.path.exists(path):
        log.error(f"Config not found: {path}"); sys.exit(1)
    with open(path) as f:
        config = json.load(f)
    for ph in ["PASTE_YOUR_CLIENT_ID", "PASTE_YOUR_NEW_CLIENT_SECRET",
                "PASTE_YOUR_REFRESH_TOKEN", "PASTE_YOUR_GMAIL_ADDRESS", "PASTE_YOUR_APP_PASSWORD"]:
        if ph in json.dumps(config):
            log.error(f"Config has placeholder: {ph}"); sys.exit(1)
    return config


def main():
    config_path = "config.json"
    test_mode = False
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--test": test_mode = True
        elif arg == "--config" and i + 1 < len(args): config_path = args[i + 1]

    log.info("=" * 60)
    log.info("CRM DAILY STALLED ALERT — STARTING")
    log.info(f"Date:    {date.today().strftime('%d-%b-%Y, %A')}")
    log.info(f"Config:  {config_path}")
    log.info(f"Mode:    {'TEST' if test_mode else 'LIVE'}")
    log.info("=" * 60)

    config = load_config(config_path)
    auth = ZohoAuth(config)
    crm = ZohoCRM(auth, config)

    # Fetch user list for Owner name resolution
    log.info("Fetching CRM users for owner resolution...")
    user_cache = crm.fetch_users()

    # Analyze Leads
    log.info("")
    log.info("--- ANALYZING LEADS ---")
    overdue_no_action, overdue_not_converted, owner_lead_alerts = \
        find_overdue_leads(crm, config, user_cache)

    # Analyze Enquiries
    log.info("")
    log.info("--- ANALYZING ENQUIRIES ---")
    stage_results, total_enq_count, owner_enq_alerts = \
        find_stalled_enquiries(crm, config, user_cache)

    has_anything = (len(overdue_no_action) > 0 or len(overdue_not_converted) > 0 or total_enq_count > 0)

    # All Clear
    if not has_anything:
        log.info(""); log.info("No stalled items. Sending all-clear.")
        html = build_all_clear_html()
        if test_mode:
            with open("test_all_clear.html", "w", encoding="utf-8") as f: f.write(html)
            log.info("Saved: test_all_clear.html")
        for r in config["email"]["summary_recipients"]:
            send_email(r, f"All Clear — {date.today().strftime('%d-%b-%Y')}", html, config, test_mode)
        log.info("Done."); return

    # --- BULK PRE-FETCH ACCOUNT NAMES ---
    # Collect all records that have Account_Name and fetch names in bulk
    log.info("")
    log.info("--- PRE-FETCHING ACCOUNT NAMES ---")
    all_enquiry_records = []
    for stage, items in stage_results.items():
        for item in items:
            all_enquiry_records.append(item["record"])
    crm.bulk_fetch_accounts(all_enquiry_records)

    # Excel Report
    log.info("")
    log.info("--- BUILDING EXCEL REPORT ---")
    excel_file = build_excel_report(
        overdue_no_action, overdue_not_converted,
        stage_results, config, user_cache, crm
    )

    # # Summary Email
    # log.info("")
    # log.info("--- BUILDING SUMMARY EMAIL ---")
    # summary_html = build_summary_html(
    #     overdue_no_action, overdue_not_converted,
    #     stage_results, total_enq_count,
    #     config, user_cache, crm
    # )

    # if test_mode:
    #     with open("test_summary_email.html", "w", encoding="utf-8") as f:
    #         f.write(summary_html)
    #     log.info("Saved: test_summary_email.html")

    # subject = f"Daily Stalled Alert Summary — {date.today().strftime('%d-%b-%Y')}"
    # for r in config["email"]["summary_recipients"]:
    #     send_email(r, subject, summary_html, config, test_mode, attachment_path=excel_file)

    # Send Excel report via email
    log.info("")
    log.info("--- SENDING REPORT ---")
    subject = f"Daily Stalled Report — {date.today().strftime('%d-%b-%Y')}"
    simple_body = f"""<html><body>
    <p>Daily stalled report attached.</p>
    <p>Leads (no action): {len(overdue_no_action)} | Leads (not converted): {len(overdue_not_converted)} | Enquiries stalled: {total_enq_count}</p>
    </body></html>"""
    for r in config["email"]["summary_recipients"]:
        send_email(r, subject, simple_body, config, test_mode, attachment_path=excel_file)

    # Owner Alerts
    if config["email"]["send_owner_alerts"]:
        log.info("")
        log.info("--- BUILDING OWNER ALERTS ---")
        all_owners = set(list(owner_lead_alerts.keys()) + list(owner_enq_alerts.keys()))
        log.info(f"Owners with stalled items: {len(all_owners)}")

        for oe in all_owners:
            la = owner_lead_alerts.get(oe, [])
            ea = owner_enq_alerts.get(oe, [])
            owner_html, count = build_owner_html(oe, la, ea, config, user_cache, crm)

            if test_mode:
                safe = oe.replace("@", "_at_").replace(".", "_")
                with open(f"test_owner_{safe}.html", "w", encoding="utf-8") as f:
                    f.write(owner_html)
                log.info(f"Saved: test_owner_{safe}.html")

            send_email(oe, f"ACTION REQUIRED: {count} stalled items — {date.today().strftime('%d-%b-%Y')}",
                       owner_html, config, test_mode)

    # Done
    log.info("")
    log.info("=" * 60)
    log.info("COMPLETED SUCCESSFULLY")
    log.info(f"  Leads (no action):     {len(overdue_no_action)}")
    log.info(f"  Leads (not converted): {len(overdue_not_converted)}")
    log.info(f"  Enquiries stalled:     {total_enq_count}")
    log.info(f"  Owner alerts sent:     {len(set(list(owner_lead_alerts.keys()) + list(owner_enq_alerts.keys())))}")
    if excel_file:
        log.info(f"  Excel report:          {excel_file}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()