"""
Excel Report Builder
=====================
Sheets: Owner Summary | Master List | Leads No Action | Leads Not Converted | Per-Stage sheets
"""

import logging
from datetime import date, datetime
from collections import defaultdict
from .analyzer import get_field_value, resolve_owner, get_kva_category, business_days_between

log = logging.getLogger(__name__)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

def _styles():
    return {
        "hf": Font(bold=True, color="FFFFFF", name="Arial", size=11),
        "hfill": PatternFill("solid", fgColor="2C3E50"),
        "ha": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "df": Font(name="Arial", size=10),
        "rf": Font(name="Arial", size=10, bold=True, color="C0392B"),
        "bf": Font(name="Arial", size=10, bold=True),
        "b": Border(left=Side("thin","CCCCCC"), right=Side("thin","CCCCCC"),
                     top=Side("thin","CCCCCC"), bottom=Side("thin","CCCCCC")),
        "redfill": PatternFill("solid", fgColor="FDECEA"),
        "yellowfill": PatternFill("solid", fgColor="FFF8E1"),
    }

def _hdr(ws, headers, s):
    for ci, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=ci, value=h)
        c.font = s["hf"]; c.fill = s["hfill"]; c.alignment = s["ha"]; c.border = s["b"]

def _autowidth(ws, headers, row_count):
    for ci in range(1, len(headers) + 1):
        col = ws.cell(row=1, column=ci).column_letter
        max_len = len(str(headers[ci-1]))
        for ri in range(2, min(row_count + 2, 102)):  # sample first 100 rows
            val = ws.cell(row=ri, column=ci).value
            if val: max_len = max(max_len, len(str(val)))
        ws.column_dimensions[col].width = min(max_len + 4, 50)

def _filter(ws, headers, row_count):
    if row_count > 0:
        end = ws.cell(row=1, column=len(headers)).column_letter
        ws.auto_filter.ref = f"A1:{end}{row_count + 1}"


def _calc_days_on_stage(record):
    """Calculate days from Created_Time to today (total days on this enquiry)."""
    created = record.get("Created_Time", "")
    if not created or str(created) == "null" or str(created) == "None":
        return "-"
    try:
        created_date = datetime.strptime(str(created)[:10], "%Y-%m-%d").date()
        return (date.today() - created_date).days
    except:
        return "-"


def build_excel_report(overdue_no_action, overdue_not_converted,
                       stage_results, config, user_cache, crm) -> str:
    if not HAS_OPENPYXL:
        log.warning("openpyxl not installed."); return None

    wb = Workbook()
    s = _styles()
    stage_names = config["stage_display_names"]
    stages = [st for st in config["stages_to_monitor"] if st not in config["terminal_stages"]]

    # ================================================================
    # SHEET 1: OWNER SUMMARY
    # ================================================================
    log.info("  Building Owner Summary...")
    ws = wb.active; ws.title = "Owner Summary"; ws.sheet_properties.tabColor = "2C3E50"

    owner_data = defaultdict(lambda: {
        "leads_na": 0, "leads_nc": 0, "total": 0, "amount": 0, "days_over": 0,
        "stages": defaultdict(int)
    })
    for item in overdue_no_action:
        n, _ = resolve_owner(item["lead"], user_cache); owner_data[n]["leads_na"] += 1
    for item in overdue_not_converted:
        n, _ = resolve_owner(item["lead"], user_cache); owner_data[n]["leads_nc"] += 1
    for stage, items in stage_results.items():
        for item in items:
            n, _ = resolve_owner(item["record"], user_cache)
            od = owner_data[n]; od["total"] += 1; od["stages"][stage] += 1
            od["days_over"] += max(0, item["days_stalled"] - item["threshold"])
            amt = item["record"].get("Amount")
            if amt and str(amt) not in ("null","None"):
                try: od["amount"] += float(amt)
                except: pass

    hdrs = ["Owner", "Leads (No Action)", "Leads (Not Conv.)", "Total Enq Stalled"]
    for st in stages: hdrs.append(stage_names.get(st, st))
    hdrs.extend(["Total Amount (₹)", "Total Days Over", "Avg Days Over"])
    _hdr(ws, hdrs, s)

    sorted_owners = sorted(owner_data.items(), key=lambda x: x[1]["total"], reverse=True)
    for ri, (name, od) in enumerate(sorted_owners, 2):
        row = [name, od["leads_na"], od["leads_nc"], od["total"]]
        for st in stages: row.append(od["stages"].get(st, 0))
        avg = round(od["days_over"] / od["total"], 1) if od["total"] > 0 else 0
        row.extend([od["amount"], od["days_over"], avg])
        for ci, val in enumerate(row, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.border = s["b"]; c.font = s["df"]
            if ci == 4 and val > 20: c.font = s["rf"]; c.fill = s["redfill"]
            if ci == len(row) and val > 5: c.font = s["rf"]; c.fill = s["redfill"]
        ws.cell(row=ri, column=len(hdrs)-2).number_format = '#,##0'
    _autowidth(ws, hdrs, len(sorted_owners)); _filter(ws, hdrs, len(sorted_owners))
    ws.freeze_panes = "A2"

    # ================================================================
    # SHEET 2: MASTER LIST
    # ================================================================
    log.info("  Building Master List...")
    ws2 = wb.create_sheet("Master List"); ws2.sheet_properties.tabColor = "E74C3C"

    m_hdrs = [
        "Owner", "Customer Name", "Enquiry Name", "Enq No.", "Stage",
        "kVA", "Offering", "Amount (₹)", "Days on Stage", "Threshold",
        "Over By", "Enquiry Age (Days)", "Created Date", "Last Updated", "Remarks"
    ]
    _hdr(ws2, m_hdrs, s)

    master = []
    for stage, items in stage_results.items():
        for item in items:
            rec = item["record"]
            owner_name, _ = resolve_owner(rec, user_cache)
            over_by = max(0, item["days_stalled"] - item["threshold"])
            age = _calc_days_on_stage(rec)
            created = get_field_value(rec, "Created_Time", user_cache, crm)
            updated = get_field_value(rec, "Modified_Time", user_cache, crm)
            amt = None
            raw_amt = rec.get("Amount")
            if raw_amt and str(raw_amt) not in ("null","None"):
                try: amt = float(raw_amt)
                except: pass
            master.append({
                "row": [
                    owner_name,
                    get_field_value(rec, "Account_Name", user_cache, crm),
                    get_field_value(rec, "Deal_Name", user_cache, crm),
                    get_field_value(rec, "ENQ_NUM", user_cache, crm),
                    stage_names.get(stage, stage),
                    get_field_value(rec, "DG_KVA", user_cache, crm),
                    get_field_value(rec, "OFFERING", user_cache, crm),
                    amt,
                    item["days_stalled"],
                    item["threshold"],
                    over_by,
                    age,
                    created[:10] if created != "-" and len(created) >= 10 else created,
                    updated[:10] if updated != "-" and len(updated) >= 10 else updated,
                    get_field_value(rec, "Status_Remarks", user_cache, crm),
                ],
                "over_by": over_by
            })

    master.sort(key=lambda x: (x["row"][0], -x["over_by"]))

    for ri, item in enumerate(master, 2):
        row = item["row"]
        for ci, val in enumerate(row, 1):
            c = ws2.cell(row=ri, column=ci, value=val)
            c.border = s["b"]; c.font = s["df"]
        # Highlight Over By (col 11)
        ob = ws2.cell(row=ri, column=11)
        if item["over_by"] >= 10: ob.font = s["rf"]; ob.fill = s["redfill"]
        elif item["over_by"] >= 5: ob.font = s["bf"]; ob.fill = s["yellowfill"]
        # Amount format (col 8)
        if row[7] is not None: ws2.cell(row=ri, column=8).number_format = '#,##0'

    _autowidth(ws2, m_hdrs, len(master)); _filter(ws2, m_hdrs, len(master))
    ws2.freeze_panes = "A2"

    # ================================================================
    # SHEET 3 & 4: LEADS
    # ================================================================
    log.info("  Building Lead sheets...")
    l_hdrs = [c["label"] for c in config["lead_columns"]] + ["Created Date", "Lead Age (Days)", "Biz Days Overdue"]

    def _lead_sheet(ws_l, items, color):
        ws_l.sheet_properties.tabColor = color; _hdr(ws_l, l_hdrs, s)
        for ri, item in enumerate(items, 2):
            row = [get_field_value(item["lead"], c["field"], user_cache, crm) for c in config["lead_columns"]]
            # Created Date
            created = get_field_value(item["lead"], "Created_Time", user_cache, crm)
            created_short = created[:10] if created != "-" and len(created) >= 10 else created
            # Lead Age = calendar days from created to today
            age = _calc_days_on_stage(item["lead"])
            row.extend([created_short, age, item["biz_days"]])
            for ci, val in enumerate(row, 1):
                c = ws_l.cell(row=ri, column=ci, value=val)
                c.border = s["b"]; c.font = s["rf"] if ci == len(row) else s["df"]
        _autowidth(ws_l, l_hdrs, len(items)); _filter(ws_l, l_hdrs, len(items))
        ws_l.freeze_panes = "A2"

    _lead_sheet(wb.create_sheet("Leads - No Action"), overdue_no_action, "C0392B")
    _lead_sheet(wb.create_sheet("Leads - Not Converted"), overdue_not_converted, "E67E22")

    # ================================================================
    # SHEET 5+: PER STAGE
    # ================================================================
    log.info("  Building per-stage sheets...")
    e_hdrs = [c["label"] for c in config["enquiry_columns"]] + [
        "kVA Category", "Threshold", "Days on Stage", "Over By", "Enquiry Age (Days)"
    ]

    for stage in stages:
        items = stage_results.get(stage, [])
        if not items: continue
        display = stage_names.get(stage, stage)
        ws_stg = wb.create_sheet(display[:31])
        ws_stg.sheet_properties.tabColor = config["stage_colors"].get(stage, "2c3e50").replace("#", "")
        _hdr(ws_stg, e_hdrs, s)

        for ri, item in enumerate(items, 2):
            rec = item["record"]
            over_by = max(0, item["days_stalled"] - item["threshold"])
            age = _calc_days_on_stage(rec)
            row = [get_field_value(rec, c["field"], user_cache, crm) for c in config["enquiry_columns"]]
            row.extend([item["kva_category"], f"{item['threshold']} day(s)", item["days_stalled"], over_by, age])
            for ci, val in enumerate(row, 1):
                c = ws_stg.cell(row=ri, column=ci, value=val)
                c.border = s["b"]; c.font = s["df"]
            # Highlight Over By
            ob_ci = len(row) - 1  # Over By column
            ob = ws_stg.cell(row=ri, column=ob_ci)
            if over_by >= 10: ob.font = s["rf"]; ob.fill = s["redfill"]
            elif over_by >= 5: ob.font = s["bf"]; ob.fill = s["yellowfill"]

        _autowidth(ws_stg, e_hdrs, len(items)); _filter(ws_stg, e_hdrs, len(items))
        ws_stg.freeze_panes = "A2"

    # ================================================================
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    filename = f"stalled_report_{timestamp}.xlsx"
    wb.save(filename)
    log.info(f"  Excel saved: {filename}")
    return filename