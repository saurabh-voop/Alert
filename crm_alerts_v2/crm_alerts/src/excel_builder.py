"""
Excel Report Builder
=====================
Generates .xlsx with:
1. Owner Summary (pivot-style — worst performers at top)
2. Master List (all stalled enquiries sorted by Owner → Days Over)
3. Leads - No Action
4. Leads - Not Converted
5. One sheet per enquiry stage
"""

import logging
from datetime import date
from datetime import datetime
from collections import defaultdict
from .analyzer import get_field_value, resolve_owner, get_kva_category

log = logging.getLogger(__name__)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False


# ============================================================================
# STYLES
# ============================================================================

def _styles():
    return {
        "hdr_font": Font(bold=True, color="FFFFFF", name="Arial", size=11),
        "hdr_fill": PatternFill("solid", fgColor="2C3E50"),
        "hdr_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "data_font": Font(name="Arial", size=10),
        "red_font": Font(name="Arial", size=10, bold=True, color="C0392B"),
        "green_font": Font(name="Arial", size=10, color="27AE60"),
        "bold_font": Font(name="Arial", size=10, bold=True),
        "border": Border(
            left=Side("thin", "CCCCCC"), right=Side("thin", "CCCCCC"),
            top=Side("thin", "CCCCCC"), bottom=Side("thin", "CCCCCC")
        ),
        "red_fill": PatternFill("solid", fgColor="FDECEA"),
        "green_fill": PatternFill("solid", fgColor="E8F5E9"),
        "yellow_fill": PatternFill("solid", fgColor="FFF8E1"),
    }


def _write_headers(ws, headers, s):
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = s["hdr_font"]; c.fill = s["hdr_fill"]
        c.alignment = s["hdr_align"]; c.border = s["border"]


def _auto_width(ws, headers, rows):
    for ci in range(1, len(headers) + 1):
        vals = [str(headers[ci - 1])]
        for r in rows:
            if ci <= len(r):
                vals.append(str(r[ci - 1]) if r[ci - 1] is not None else "")
        max_len = max(len(v) for v in vals)
        col_letter = ws.cell(row=1, column=ci).column_letter
        ws.column_dimensions[col_letter].width = min(max_len + 4, 50)


def _add_filter(ws, headers, row_count):
    if row_count > 0:
        end_col = ws.cell(row=1, column=len(headers)).column_letter
        ws.auto_filter.ref = f"A1:{end_col}{row_count + 1}"


# ============================================================================
# MAIN BUILDER
# ============================================================================

def build_excel_report(overdue_no_action, overdue_not_converted,
                       stage_results, config, user_cache, crm) -> str:
    if not HAS_OPENPYXL:
        log.warning("openpyxl not installed. Run: pip install openpyxl")
        return None

    wb = Workbook()
    s = _styles()
    stage_names = config["stage_display_names"]
    stages_to_monitor = [st for st in config["stages_to_monitor"]
                         if st not in config["terminal_stages"]]

    # ================================================================
    # SHEET 1: OWNER SUMMARY
    # ================================================================
    log.info("  Building Owner Summary...")
    ws = wb.active
    ws.title = "Owner Summary"
    ws.sheet_properties.tabColor = "2C3E50"

    # Collect data per owner
    owner_data = defaultdict(lambda: {
        "leads_no_action": 0, "leads_not_converted": 0,
        "total_stalled": 0, "total_amount": 0, "total_days_over": 0,
        "stages": defaultdict(int)
    })

    for item in overdue_no_action:
        name, _ = resolve_owner(item["lead"], user_cache)
        owner_data[name]["leads_no_action"] += 1

    for item in overdue_not_converted:
        name, _ = resolve_owner(item["lead"], user_cache)
        owner_data[name]["leads_not_converted"] += 1

    for stage, items in stage_results.items():
        for item in items:
            name, _ = resolve_owner(item["record"], user_cache)
            od = owner_data[name]
            od["total_stalled"] += 1
            od["stages"][stage] += 1
            od["total_days_over"] += max(0, item["days_stalled"] - item["threshold"])
            amt = item["record"].get("Amount")
            if amt and str(amt) != "null" and str(amt) != "None":
                try:
                    od["total_amount"] += float(amt)
                except:
                    pass

    # Headers
    summary_headers = [
        "Owner", "Leads (No Action)", "Leads (Not Converted)",
        "Total Enquiries Stalled"
    ]
    for st in stages_to_monitor:
        summary_headers.append(stage_names.get(st, st))
    summary_headers.extend(["Total Amount (₹)", "Total Days Over", "Avg Days Over"])

    _write_headers(ws, summary_headers, s)

    # Rows — sorted by total stalled descending
    sorted_owners = sorted(owner_data.items(),
                           key=lambda x: x[1]["total_stalled"], reverse=True)

    summary_rows = []
    for ri, (owner_name, od) in enumerate(sorted_owners, 2):
        row = [
            owner_name,
            od["leads_no_action"],
            od["leads_not_converted"],
            od["total_stalled"]
        ]
        for st in stages_to_monitor:
            row.append(od["stages"].get(st, 0))
        avg_over = round(od["total_days_over"] / od["total_stalled"], 1) if od["total_stalled"] > 0 else 0
        row.extend([od["total_amount"], od["total_days_over"], avg_over])
        summary_rows.append(row)

        for ci, val in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.border = s["border"]
            c.font = s["data_font"]

            # Highlight high values
            if ci == 4 and val > 20:  # Total stalled
                c.font = s["red_font"]
                c.fill = s["red_fill"]
            elif ci == len(row) and val > 5:  # Avg days over
                c.font = s["red_font"]
                c.fill = s["red_fill"]

        # Format amount column
        amt_col = len(summary_headers) - 2
        amt_cell = ws.cell(row=ri, column=amt_col)
        amt_cell.number_format = '#,##0'

    _auto_width(ws, summary_headers, summary_rows)
    _add_filter(ws, summary_headers, len(summary_rows))

    # Freeze top row
    ws.freeze_panes = "A2"

    # ================================================================
    # SHEET 2: MASTER LIST (all stalled enquiries, sorted by Owner)
    # ================================================================
    log.info("  Building Master List...")
    ws_master = wb.create_sheet("Master List")
    ws_master.sheet_properties.tabColor = "E74C3C"

    master_headers = [
        "Owner", "Customer Name", "Enquiry Name", "Enq No.",
        "Stage", "kVA", "Offering", "Amount (₹)",
        "Days Stalled", "Threshold", "Over By",
        "Created Date", "Last Updated", "Remarks"
    ]
    _write_headers(ws_master, master_headers, s)

    # Collect all enquiry items with owner name
    master_items = []
    for stage, items in stage_results.items():
        for item in items:
            rec = item["record"]
            owner_name, _ = resolve_owner(rec, user_cache)
            over_by = max(0, item["days_stalled"] - item["threshold"])
            master_items.append({
                "owner": owner_name,
                "customer": get_field_value(rec, "Account_Name", user_cache, crm),
                "enquiry": get_field_value(rec, "Deal_Name", user_cache, crm),
                "enq_num": get_field_value(rec, "ENQ_NUM", user_cache, crm),
                "stage": stage_names.get(stage, stage),
                "kva": get_field_value(rec, "DG_KVA", user_cache, crm),
                "offering": get_field_value(rec, "OFFERING", user_cache, crm),
                "amount": rec.get("Amount"),
                "days_stalled": item["days_stalled"],
                "threshold": item["threshold"],
                "over_by": over_by,
                "created": get_field_value(rec, "Created_Time", user_cache, crm),
                "updated": get_field_value(rec, "Modified_Time", user_cache, crm),
                "remarks": get_field_value(rec, "Status_Remarks", user_cache, crm),
            })

    # Sort by Owner → then Over By descending
    master_items.sort(key=lambda x: (x["owner"], -x["over_by"]))

    master_rows = []
    prev_owner = None
    for ri, item in enumerate(master_items, 2):
        # Format amount
        amt = None
        if item["amount"] and str(item["amount"]) != "null" and str(item["amount"]) != "None":
            try:
                amt = float(item["amount"])
            except:
                amt = None

        # Format dates — show only date part
        created = item["created"][:10] if item["created"] != "-" and len(item["created"]) >= 10 else item["created"]
        updated = item["updated"][:10] if item["updated"] != "-" and len(item["updated"]) >= 10 else item["updated"]

        row = [
            item["owner"], item["customer"], item["enquiry"], item["enq_num"],
            item["stage"], item["kva"], item["offering"], amt,
            item["days_stalled"], item["threshold"], item["over_by"],
            created, updated, item["remarks"]
        ]
        master_rows.append(row)

        for ci, val in enumerate(row, 1):
            c = ws_master.cell(row=ri, column=ci, value=val)
            c.border = s["border"]
            c.font = s["data_font"]

        # Owner grouping — light color for alternating owners
        if item["owner"] != prev_owner:
            prev_owner = item["owner"]

        # Highlight Over By
        over_cell = ws_master.cell(row=ri, column=11)
        if item["over_by"] >= 10:
            over_cell.font = s["red_font"]
            over_cell.fill = s["red_fill"]
        elif item["over_by"] >= 5:
            over_cell.font = s["bold_font"]
            over_cell.fill = s["yellow_fill"]

        # Amount formatting
        if amt is not None:
            ws_master.cell(row=ri, column=8).number_format = '#,##0'

    _auto_width(ws_master, master_headers, master_rows)
    _add_filter(ws_master, master_headers, len(master_rows))
    ws_master.freeze_panes = "A2"

    # ================================================================
    # SHEET 3 & 4: LEAD SHEETS
    # ================================================================
    log.info("  Building Lead sheets...")
    lead_headers = [c["label"] for c in config["lead_columns"]] + ["Biz Days"]

    def _write_lead_sheet(ws_l, items, tab_color):
        ws_l.sheet_properties.tabColor = tab_color
        _write_headers(ws_l, lead_headers, s)
        rows = []
        for ri, item in enumerate(items, 2):
            row = [get_field_value(item["lead"], c["field"], user_cache, crm)
                   for c in config["lead_columns"]]
            row.append(item["biz_days"])
            rows.append(row)
            for ci, val in enumerate(row, 1):
                c = ws_l.cell(row=ri, column=ci, value=val)
                c.border = s["border"]
                c.font = s["red_font"] if ci == len(row) else s["data_font"]
        _auto_width(ws_l, lead_headers, rows)
        _add_filter(ws_l, lead_headers, len(rows))
        ws_l.freeze_panes = "A2"

    ws_na = wb.create_sheet("Leads - No Action")
    _write_lead_sheet(ws_na, overdue_no_action, "C0392B")

    ws_nc = wb.create_sheet("Leads - Not Converted")
    _write_lead_sheet(ws_nc, overdue_not_converted, "E67E22")

    # ================================================================
    # SHEETS 5+: ONE PER ENQUIRY STAGE
    # ================================================================
    log.info("  Building per-stage sheets...")
    enq_headers = [c["label"] for c in config["enquiry_columns"]] + [
        "kVA Category", "Threshold", "Days Stalled", "Over By"
    ]

    for stage in stages_to_monitor:
        items = stage_results.get(stage, [])
        if not items:
            continue

        display = stage_names.get(stage, stage)
        sheet_name = display[:31]
        color = config["stage_colors"].get(stage, "2c3e50").replace("#", "")

        ws_stg = wb.create_sheet(sheet_name)
        ws_stg.sheet_properties.tabColor = color
        _write_headers(ws_stg, enq_headers, s)

        rows = []
        for ri, item in enumerate(items, 2):
            rec = item["record"]
            over_by = max(0, item["days_stalled"] - item["threshold"])
            row = [get_field_value(rec, c["field"], user_cache, crm)
                   for c in config["enquiry_columns"]]
            row.extend([
                item["kva_category"],
                f"{item['threshold']} day(s)",
                item["days_stalled"],
                over_by
            ])
            rows.append(row)

            for ci, val in enumerate(row, 1):
                c = ws_stg.cell(row=ri, column=ci, value=val)
                c.border = s["border"]
                c.font = s["data_font"]

            # Highlight Over By column
            ob_cell = ws_stg.cell(row=ri, column=len(row))
            if over_by >= 10:
                ob_cell.font = s["red_font"]; ob_cell.fill = s["red_fill"]
            elif over_by >= 5:
                ob_cell.font = s["bold_font"]; ob_cell.fill = s["yellow_fill"]

        _auto_width(ws_stg, enq_headers, rows)
        _add_filter(ws_stg, enq_headers, len(rows))
        ws_stg.freeze_panes = "A2"

    # ================================================================
    # SAVE
    # ================================================================
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    filename = f"stalled_report_{timestamp}.xlsx"
    wb.save(filename)
    log.info(f"  Excel saved: {filename}")
    return filename