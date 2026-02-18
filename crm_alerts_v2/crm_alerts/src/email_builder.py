"""
Email Builder
==============
Builds HTML emails for summary + owner alerts.
Passes user_cache and crm to get_field_value for Owner/Account name resolution.
"""

import logging
from datetime import date
from .analyzer import get_field_value

log = logging.getLogger(__name__)

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


def build_all_clear_html() -> str:
    today_str = date.today().strftime("%d-%b-%Y, %A")
    return f"""<html><head>{CSS}</head><body>
    <h2 style='color:#27ae60;'>Daily Stalled Alert — All Clear</h2>
    <p>Date: {today_str}</p>
    <div class='ok-box'>
    No overdue leads or stalled enquiries found. All items are within their deadlines.
    </div></body></html>"""


def build_summary_html(overdue_no_action, overdue_not_converted,
                       stage_results, total_enq_count,
                       config, user_cache, crm) -> str:
    today_str = date.today().strftime("%d-%b-%Y, %A")
    a_days = config["lead_thresholds"]["no_action_days"]
    c_days = config["lead_thresholds"]["not_converted_days"]

    html = f"<html><head>{CSS}</head><body>"
    html += f"<h2>Daily Stalled Alert Summary</h2>"
    html += f"<p>Report Date: <strong>{today_str}</strong></p>"

    # Summary Box
    html += "<div class='summary-box'>"
    html += f"<strong>LEADS:</strong><br>"
    html += f"&nbsp;&nbsp;No action taken (>{a_days} biz day): <strong>{len(overdue_no_action)}</strong><br>"
    html += f"&nbsp;&nbsp;Not converted (>{c_days} biz days): <strong>{len(overdue_not_converted)}</strong><br><br>"
    html += f"<strong>ENQUIRIES STALLED:</strong> <strong>{total_enq_count}</strong><br>"
    for stage in config["stages_to_monitor"]:
        if stage in config["terminal_stages"]:
            continue
        display = config["stage_display_names"].get(stage, stage)
        if stage in stage_results:
            cnt = len(stage_results[stage])
            if cnt > 0:
                html += f"&nbsp;&nbsp;&nbsp;&nbsp;• {display}: <strong>{cnt}</strong><br>"
    html += "</div>"

    # Threshold Reference
    html += "<p style='font-size:12px;color:#666;'><strong>Threshold Reference:</strong></p>"
    html += "<table class='threshold-table'><tr><th>kVA Category</th><th>Yet To Quote</th><th>Quoted</th><th>Finalization</th></tr>"
    for cat in config["kva_categories"]:
        html += f"<tr><td>{cat['label']}</td><td>{cat['yet_to_quote_days']} day(s)</td><td>{cat['quoted_days']} day(s)</td><td>{cat['finalization_days']} day(s)</td></tr>"
    html += "</table>"

    # Lead Tables
    html += "<hr class='divider'>"
    html += _section(f"LEADS — No Action Taken (>{a_days} Biz Day)", "#c0392b", len(overdue_no_action))
    if overdue_no_action:
        html += _lead_table(overdue_no_action, config, user_cache, crm)
    else:
        html += "<div class='ok-box'>All leads have been actioned on time.</div>"

    html += _section(f"LEADS — Not Converted to Enquiry (>{c_days} Biz Days)", "#e67e22", len(overdue_not_converted))
    if overdue_not_converted:
        html += _lead_table(overdue_not_converted, config, user_cache, crm)
    else:
        html += "<div class='ok-box'>All leads converted on time.</div>"

    # Enquiry Tables
    html += "<hr class='divider'><h2 style='color:#2c3e50;'>STALLED ENQUIRIES — By Stage</h2>"
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
        html += _section(display, color, len(items))
        html += _enq_table(items, config, user_cache, crm)

    if not has_any:
        html += "<div class='ok-box'>No stalled enquiries. All moving within deadlines.</div>"

    # Footer
    html += f"<div class='footer'>Automated report | Lead action {a_days} biz day, Lead conversion {c_days} biz days, Enquiry thresholds vary by kVA. Business days = Mon-Fri only.</div>"
    html += "</body></html>"
    return html


def build_owner_html(owner_email, lead_alerts, enq_alerts,
                     config, user_cache, crm) -> tuple:
    today_str = date.today().strftime("%d-%b-%Y, %A")
    total = 0

    html = f"<html><head>{CSS}</head><body>"
    html += "<h2 style='color:#c0392b;'>Your Stalled Items — Action Required</h2>"
    html += f"<p>Date: {today_str}</p>"
    html += "<p>The following items assigned to you are stalled. Please take action today.</p>"

    if lead_alerts:
        total += len(lead_alerts)
        html += _section("Your Overdue Leads", "#c0392b", len(lead_alerts))
        html += "<table><tr><th>#</th><th>Lead Name</th><th>Company</th><th>Phone</th><th>Issue</th><th>Biz Days</th></tr>"
        for i, item in enumerate(lead_alerts, 1):
            ld = item["lead"]
            html += f"<tr><td>{i}</td>"
            html += f"<td>{get_field_value(ld, 'Last_Name', user_cache, crm)}</td>"
            html += f"<td>{get_field_value(ld, 'Company', user_cache, crm)}</td>"
            html += f"<td>{get_field_value(ld, 'Phone', user_cache, crm)}</td>"
            html += f"<td style='color:#c0392b;'>{item['type']}</td>"
            html += f"<td style='font-weight:bold;'>{item['days']}</td></tr>"
        html += "</table>"

    if enq_alerts:
        total += len(enq_alerts)
        html += _section("Your Stalled Enquiries", "#e67e22", len(enq_alerts))
        html += "<table><tr><th>#</th><th>Enquiry</th><th>kVA</th><th>Stage</th><th>Category</th><th>Threshold</th><th>Days Stalled</th></tr>"
        for i, item in enumerate(enq_alerts, 1):
            rec = item["record"]
            stg = config["stage_display_names"].get(item["stage"], item["stage"])
            html += f"<tr><td>{i}</td>"
            html += f"<td>{get_field_value(rec, 'Deal_Name', user_cache, crm)}</td>"
            html += f"<td>{get_field_value(rec, 'DG_KVA', user_cache, crm)}</td>"
            html += f"<td>{stg}</td><td>{item['kva_category']}</td>"
            html += f"<td>{item['threshold']} day(s)</td>"
            html += f"<td style='color:#c0392b;font-weight:bold;'>{item['days_stalled']}</td></tr>"
        html += "</table>"

    html += "<div class='footer'>Automated alert. Update CRM after taking action.</div></body></html>"
    return html, total


# --- Helpers ---

def _section(title, color, count):
    return f"<h3 style='background-color:{color};'>{title} <span class='count-badge'>{count}</span></h3>"

def _lead_table(items, config, user_cache, crm):
    cols = config["lead_columns"]
    html = "<table><tr><th>#</th>"
    for c in cols:
        html += f"<th>{c['label']}</th>"
    html += "<th>Biz Days</th></tr>"
    for i, item in enumerate(items, 1):
        html += f"<tr><td>{i}</td>"
        for c in cols:
            html += f"<td>{get_field_value(item['lead'], c['field'], user_cache, crm)}</td>"
        html += f"<td style='color:#c0392b;font-weight:bold;'>{item['biz_days']}</td></tr>"
    html += "</table>"
    return html

def _enq_table(items, config, user_cache, crm):
    cols = config["enquiry_columns"]
    html = "<table><tr><th>#</th>"
    for c in cols:
        html += f"<th>{c['label']}</th>"
    html += "<th>Category</th><th>Threshold</th><th>Days Stalled</th></tr>"
    for i, item in enumerate(items, 1):
        html += f"<tr><td>{i}</td>"
        for c in cols:
            html += f"<td>{get_field_value(item['record'], c['field'], user_cache, crm)}</td>"
        html += f"<td>{item['kva_category']}</td><td>{item['threshold']} day(s)</td>"
        html += f"<td style='color:#c0392b;font-weight:bold;'>{item['days_stalled']}</td></tr>"
    html += "</table>"
    return html
