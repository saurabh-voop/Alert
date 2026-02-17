"""
Email Builder
==============
Builds HTML emails for:
1. Summary report (MD/Management)
2. Individual owner alerts
"""

import os
import logging
from datetime import date

from .analyzer import get_field_value

log = logging.getLogger(__name__)

# ============================================================================
# CSS (shared across all emails)
# ============================================================================

CSS = """<style>
body{font-family:Arial,sans-serif;font-size:14px;color:#333;line-height:1.5;}
h2{color:#c0392b;margin-top:30px;}
h3{margin-top:25px;padding:10px 14px;color:white;border-radius:4px;font-size:15px;}
table{border-collapse:collapse;width:100%;margin-bottom:20px;}
th{background-color:#2c3e50;color:white;padding:10px;text-align:left;font-size:13px;}
td{padding:8px 10px;border-bottom:1px solid #ddd;font-size:13px;}
tr:nth-child(even){background-color:#f9f9f9;}
.summary-box{background-color:#fdf2f2;border-left:4px solid #c0392b;padding:15px;margin:15px 0;border-radius:4px;}
.ok-box{background-color:#f0fdf0;border-left:4px solid #27ae60;padding:15px;margin:15px 0;border-radius:4px;}
.count-badge{display:inline-block;background:rgba(255,255,255,0.3);color:white;padding:2px 10px;border-radius:10px;font-size:13px;font-weight:bold;margin-left:8px;}
.divider{border:none;border-top:2px solid #eee;margin:30px 0;}
.footer{margin-top:30px;padding-top:15px;border-top:1px solid #ddd;font-size:12px;color:#888;}
.threshold-table{width:auto;}
.threshold-table td,.threshold-table th{padding:6px 12px;font-size:12px;}
</style>"""


# ============================================================================
# ALL-CLEAR EMAIL
# ============================================================================

def build_all_clear_html() -> str:
    """Build the 'no issues found' email."""
    today_str = date.today().strftime("%d-%b-%Y, %A")
    return f"""<html><head>{CSS}</head><body>
    <h2 style='color:#27ae60;'>Daily Overdue Alert — All Clear</h2>
    <p>Date: {today_str}</p>
    <div class='ok-box'>
    No overdue leads or stalled enquiries found. All items are within their deadlines.
    </div></body></html>"""


# ============================================================================
# SUMMARY EMAIL (MD/Management)
# ============================================================================

def build_summary_html(overdue_no_action: list, overdue_not_converted: list,
                       stage_results: dict, total_enq_count: int,
                       config: dict) -> str:
    """Build the full summary HTML email."""

    today_str = date.today().strftime("%d-%b-%Y, %A")
    action_days = config["lead_thresholds"]["no_action_days"]
    convert_days = config["lead_thresholds"]["not_converted_days"]

    html = f"<html><head>{CSS}</head><body>"
    html += f"<h2>Daily Overdue Alert Summary</h2>"
    html += f"<p>Report Date: <strong>{today_str}</strong></p>"

    # --- Summary Box ---
    html += _build_summary_box(
        overdue_no_action, overdue_not_converted,
        stage_results, total_enq_count, config
    )

    # --- Threshold Reference ---
    html += _build_threshold_table(config)

    # --- Lead Tables ---
    html += "<hr class='divider'>"
    html += _build_section_header(
        f"LEADS — No Action Taken (>{action_days} Biz Day)",
        "#c0392b", len(overdue_no_action)
    )
    if overdue_no_action:
        html += _build_lead_table(overdue_no_action, config)
    else:
        html += "<div class='ok-box'>All leads have been actioned on time.</div>"

    html += _build_section_header(
        f"LEADS — Not Converted to Enquiry (>{convert_days} Biz Days)",
        "#e67e22", len(overdue_not_converted)
    )
    if overdue_not_converted:
        html += _build_lead_table(overdue_not_converted, config)
    else:
        html += "<div class='ok-box'>All leads converted on time.</div>"

    # --- Enquiry Tables ---
    html += "<hr class='divider'>"
    html += "<h2 style='color:#2c3e50;'>stalled ENQUIRIES — By Stage</h2>"

    has_any = False
    for stage in config["stages_to_monitor"]:
        if stage in config["terminal_stages"]:
            continue
        if stage not in stage_results:
            continue
        items = stage_results[stage]
        if not items:
            continue

        has_any = True
        display = config["stage_display_names"].get(stage, stage)
        color = config["stage_colors"].get(stage, "#2c3e50")

        html += _build_section_header(display, color, len(items))
        html += _build_enquiry_table(items, config)

    if not has_any:
        html += "<div class='ok-box'>No stalled enquiries. All moving within deadlines.</div>"

    # --- Footer ---
    html += _build_footer(config)
    html += "</body></html>"

    return html


# ============================================================================
# OWNER ALERT EMAIL
# ============================================================================

def build_owner_html(owner_email: str, lead_alerts: list,
                     enq_alerts: list, config: dict) -> tuple:
    """
    Build HTML email for an individual owner.

    Returns:
        (html_string, total_item_count)
    """
    today_str = date.today().strftime("%d-%b-%Y, %A")
    total_items = 0

    html = f"<html><head>{CSS}</head><body>"
    html += "<h2 style='color:#c0392b;'>Your Overdue Items — Action Required</h2>"
    html += f"<p>Date: {today_str}</p>"
    html += "<p>The following leads and enquiries assigned to you are overdue. "
    html += "Please take action today.</p>"

    # --- Owner's leads ---
    if lead_alerts:
        total_items += len(lead_alerts)
        html += _build_section_header(
            "Your Overdue Leads", "#c0392b", len(lead_alerts)
        )
        html += "<table><tr><th>#</th><th>Lead Name</th><th>Company</th>"
        html += "<th>Phone</th><th>Issue</th><th>Biz Days</th></tr>"

        for i, item in enumerate(lead_alerts, 1):
            lead = item["lead"]
            html += f"<tr><td>{i}</td>"
            html += f"<td>{get_field_value(lead, 'Last_Name')}</td>"
            html += f"<td>{get_field_value(lead, 'Company')}</td>"
            html += f"<td>{get_field_value(lead, 'Phone')}</td>"
            html += f"<td style='color:#c0392b;'>{item['type']}</td>"
            html += f"<td style='font-weight:bold;'>{item['days']}</td></tr>"

        html += "</table>"

    # --- Owner's enquiries ---
    if enq_alerts:
        total_items += len(enq_alerts)
        html += _build_section_header(
            "Your stalled Enquiries", "#e67e22", len(enq_alerts)
        )
        html += "<table><tr><th>#</th><th>Enquiry</th><th>kVA</th>"
        html += "<th>Stage</th><th>Category</th><th>Threshold</th>"
        html += "<th>Days stalled</th></tr>"

        stage_names = config["stage_display_names"]
        for i, item in enumerate(enq_alerts, 1):
            rec = item["record"]
            stg_display = stage_names.get(item["stage"], item["stage"])
            html += f"<tr><td>{i}</td>"
            html += f"<td>{get_field_value(rec, 'Deal_Name')}</td>"
            html += f"<td>{get_field_value(rec, 'DG_KVA')}</td>"
            html += f"<td>{stg_display}</td>"
            html += f"<td>{item['kva_category']}</td>"
            html += f"<td>{item['threshold']} day(s)</td>"
            html += f"<td style='color:#c0392b;font-weight:bold;'>"
            html += f"{item['days_stalled']}</td></tr>"

        html += "</table>"

    # --- Footer ---
    html += "<div class='footer'>"
    html += "Automated alert. Please update CRM records after taking action. "
    html += "If a lead is not relevant, mark it as Junk/Not Qualified. "
    html += "If an enquiry is on hold, update Status Remarks."
    html += "</div></body></html>"

    return html, total_items


# ============================================================================
# PRIVATE HELPERS — TABLE BUILDERS
# ============================================================================

def _build_summary_box(overdue_no_action, overdue_not_converted,
                       stage_results, total_enq_count, config) -> str:
    """Build the red summary box at the top of the email."""
    action_days = config["lead_thresholds"]["no_action_days"]
    convert_days = config["lead_thresholds"]["not_converted_days"]

    html = "<div class='summary-box'>"
    html += "<strong>LEADS:</strong><br>"
    html += (f"&nbsp;&nbsp;No action taken (>{action_days} biz day): "
             f"<strong>{len(overdue_no_action)}</strong><br>")
    html += (f"&nbsp;&nbsp;Not converted (>{convert_days} biz days): "
             f"<strong>{len(overdue_not_converted)}</strong><br><br>")
    html += f"<strong>ENQUIRIES stalled:</strong> <strong>{total_enq_count}</strong><br>"

    for stage in config["stages_to_monitor"]:
        if stage in config["terminal_stages"]:
            continue
        display = config["stage_display_names"].get(stage, stage)
        if stage in stage_results:
            cnt = len(stage_results[stage])
            if cnt > 0:
                html += (f"&nbsp;&nbsp;&nbsp;&nbsp;• {display}: "
                         f"<strong>{cnt}</strong><br>")

    html += "</div>"
    return html


def _build_threshold_table(config) -> str:
    """Build the kVA threshold reference table."""
    html = "<p style='font-size:12px;color:#666;'>"
    html += "<strong>Threshold Reference:</strong></p>"
    html += "<table class='threshold-table'>"
    html += "<tr><th>kVA Category</th><th>Yet To Quote</th>"
    html += "<th>Quoted</th><th>Finalization</th></tr>"

    for cat in config["kva_categories"]:
        html += f"<tr><td>{cat['label']}</td>"
        html += f"<td>{cat['yet_to_quote_days']} day(s)</td>"
        html += f"<td>{cat['quoted_days']} day(s)</td>"
        html += f"<td>{cat['finalization_days']} day(s)</td></tr>"

    html += "</table>"
    return html


def _build_section_header(title: str, color: str, count: int) -> str:
    """Build a colored section header with count badge."""
    return (f"<h3 style='background-color:{color};'>{title} "
            f"<span class='count-badge'>{count}</span></h3>")


def _build_lead_table(items: list, config: dict) -> str:
    """Build an HTML table for lead items."""
    cols = config["lead_columns"]

    html = "<table><tr><th>#</th>"
    for col in cols:
        html += f"<th>{col['label']}</th>"
    html += "<th>Biz Days</th></tr>"

    for i, item in enumerate(items, 1):
        lead = item["lead"]
        days = item["biz_days"]
        html += f"<tr><td>{i}</td>"
        for col in cols:
            html += f"<td>{get_field_value(lead, col['field'])}</td>"
        html += (f"<td style='color:#c0392b;font-weight:bold;'>"
                 f"{days}</td></tr>")

    html += "</table>"
    return html


def _build_enquiry_table(items: list, config: dict) -> str:
    """Build an HTML table for enquiry items."""
    cols = config["enquiry_columns"]

    html = "<table><tr><th>#</th>"
    for col in cols:
        html += f"<th>{col['label']}</th>"
    html += "<th>Category</th><th>Threshold</th><th>Days stalled</th></tr>"

    for i, item in enumerate(items, 1):
        rec = item["record"]
        html += f"<tr><td>{i}</td>"
        for col in cols:
            html += f"<td>{get_field_value(rec, col['field'])}</td>"
        html += f"<td>{item['kva_category']}</td>"
        html += f"<td>{item['threshold']} day(s)</td>"
        html += (f"<td style='color:#c0392b;font-weight:bold;'>"
                 f"{item['days_stalled']}</td></tr>")

    html += "</table>"
    return html


def _build_footer(config: dict) -> str:
    """Build the email footer."""
    action_days = config["lead_thresholds"]["no_action_days"]
    convert_days = config["lead_thresholds"]["not_converted_days"]

    html = "<div class='footer'>"
    html += (f"Automated report | Thresholds: Lead action {action_days} biz day, "
             f"Lead conversion {convert_days} biz days, "
             f"Enquiry thresholds vary by kVA. "
             f"Business days = Mon-Fri only. Public holidays not excluded.")
    html += "</div>"
    return html
