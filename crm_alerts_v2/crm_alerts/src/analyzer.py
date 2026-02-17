"""
Overdue Analyzer
=================
Core business logic:
- Business day calculation (Mon-Fri, excludes weekends)
- kVA-based threshold lookup
- Overdue lead detection (via COQL)
- stalled enquiry detection (via COQL)
"""

import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

log = logging.getLogger(__name__)


# ============================================================================
# BUSINESS DAY CALCULATOR
# ============================================================================

def business_days_between(start, end=None) -> int:
    """
    Count weekdays (Mon-Fri) between start and end dates.
    Does NOT exclude public holidays.
    """
    if end is None:
        end = date.today()

    if isinstance(start, str):
        start = datetime.strptime(start[:10], "%Y-%m-%d").date()
    elif isinstance(start, datetime):
        start = start.date()

    if isinstance(end, str):
        end = datetime.strptime(end[:10], "%Y-%m-%d").date()
    elif isinstance(end, datetime):
        end = end.date()

    count = 0
    current = start
    while current < end:
        if current.weekday() < 5:
            count += 1
        current += timedelta(days=1)

    return count


# ============================================================================
# FIELD VALUE EXTRACTOR
# ============================================================================

def get_field_value(record: dict, field_name: str) -> str:
    """
    Extract a field value from a CRM record.
    Handles nested fields like Owner.name, Owner.email.
    """
    if "." in field_name:
        parts = field_name.split(".")
        parent = record.get(parts[0])
        if parent and isinstance(parent, dict):
            val = parent.get(parts[1])
            if val and str(val) != "null":
                return str(val)
        return "-"

    val = record.get(field_name)
    if val is None or str(val) == "null":
        return "-"
    return str(val)


# ============================================================================
# THRESHOLD LOGIC
# ============================================================================

def get_kva_value(record: dict) -> int:
    """Extract kVA value from a record. Returns 0 if not set."""
    raw = record.get("DG_KVA")
    if raw and str(raw) != "null":
        try:
            return int(float(str(raw)))
        except (ValueError, TypeError):
            return 0
    return 0


def get_kva_category(kva_value: int, config: dict) -> str:
    """Return the category label for a given kVA value."""
    for cat in config["kva_categories"]:
        if cat["min_kva"] <= kva_value <= cat["max_kva"]:
            return cat["label"]
    return config["default_thresholds"]["label"]


def get_threshold_days(stage: str, kva_value: int, config: dict) -> int:
    """
    Return the threshold in business days for a stage + kVA combination.
    Fixed-threshold stages (WON, ORDER_BOOKED, etc.) ignore kVA.
    Variable stages (YET_TO_QUOTE, QUOTED, FINALIZATION) use kVA categories.
    """
    fixed = config.get("fixed_stage_thresholds", {})
    if stage in fixed:
        return fixed[stage]

    stage_key_map = {
        "YET_TO_QUOTE": "yet_to_quote_days",
        "QUOTED": "quoted_days",
        "FINALIZATION": "finalization_days"
    }
    stage_key = stage_key_map.get(stage)
    if not stage_key:
        return 1

    for cat in config["kva_categories"]:
        if cat["min_kva"] <= kva_value <= cat["max_kva"]:
            return cat[stage_key]

    return config["default_thresholds"].get(stage_key, 1)


# ============================================================================
# LEAD FIELDS FOR COQL
# ============================================================================

LEAD_FIELDS = [
    "id", "Last_Name", "First_Name", "Company", "Phone", "Email",
    "Owner", "Created_Time", "Modified_Time", "Last_Activity_Time",
    "Converted", "Lead_Status"
]

# ============================================================================
# ENQUIRY FIELDS FOR COQL
# ============================================================================

ENQUIRY_FIELDS = [
    "id", "Deal_Name", "Stage", "Amount", "DG_KVA",
    "Owner", "Created_Time", "Modified_Time", "Closing_Date",
    "Status_Remarks"
]


# ============================================================================
# OVERDUE LEAD DETECTION
# ============================================================================

def find_overdue_leads(crm, config: dict) -> tuple:
    """
    Fetch and analyze leads for overdue conditions using COQL.

    Returns:
        overdue_no_action: list of {"lead": record, "biz_days": int}
        overdue_not_converted: list of {"lead": record, "biz_days": int}
        owner_alerts: dict of {email: [{"lead", "type", "days"}, ...]}
    """
    today = date.today()
    action_days = config["lead_thresholds"]["no_action_days"]
    convert_days = config["lead_thresholds"]["not_converted_days"]

    # Cutoff with weekend buffer
    cutoff = today - timedelta(days=action_days + 3)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    # COQL query — fetch all unconverted leads created before cutoff
    where = (
        f"Created_Time < '{cutoff_str}T23:59:59+05:30' "
        f"and Converted = false"
    )

    log.info("Fetching unconverted leads (COQL)...")
    leads = crm.fetch_records("Leads", LEAD_FIELDS, where, max_records=1000)
    log.info(f"  Found {len(leads)} unconverted leads")

    overdue_no_action = []
    overdue_not_converted = []
    owner_alerts = defaultdict(list)

    for lead in leads:
        created = lead.get("Created_Time", "")
        if not created:
            continue

        biz_days = business_days_between(created, today)

        # --- No action taken ---
        last_activity = lead.get("Last_Activity_Time")
        no_activity = (not last_activity or str(last_activity) == "null")

        if biz_days >= action_days and no_activity:
            overdue_no_action.append({"lead": lead, "biz_days": biz_days})
            _collect_owner_alert(owner_alerts, lead, "No Action", biz_days)

        # --- Not converted ---
        if biz_days >= convert_days:
            overdue_not_converted.append({"lead": lead, "biz_days": biz_days})
            _collect_owner_alert(owner_alerts, lead, "Not Converted", biz_days)

    log.info(f"  No action: {len(overdue_no_action)} | "
             f"Not converted: {len(overdue_not_converted)}")

    return overdue_no_action, overdue_not_converted, owner_alerts


# ============================================================================
# stalled ENQUIRY DETECTION
# ============================================================================

def find_stalled_enquiries(crm, config: dict) -> tuple:
    """
    Fetch and analyze enquiries stalled beyond their thresholds using COQL.

    Returns:
        stage_results: dict of {stage: [items]}
        total_count: int
        owner_alerts: dict of {email: [items]}
    """
    today = date.today()
    module = config["zoho"]["enquiry_module"]
    stages = config["stages_to_monitor"]
    terminal = config["terminal_stages"]

    stage_results = {}
    total_count = 0
    owner_alerts = defaultdict(list)

    for stage in stages:
        if stage in terminal:
            continue

        # Broad filter: modified more than 1 day ago
        cutoff = today - timedelta(days=1)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        where = (
            f"Stage = '{stage}' "
            f"and Modified_Time < '{cutoff_str}T23:59:59+05:30'"
        )

        log.info(f"Fetching enquiries at stage: {stage}...")
        records = crm.fetch_records(module, ENQUIRY_FIELDS, where,
                                    max_records=1000)

        overdue_items = []

        for rec in records:
            kva_value = get_kva_value(rec)
            threshold = get_threshold_days(stage, kva_value, config)

            mod_time = rec.get("Modified_Time", "")
            if not mod_time:
                continue

            biz_days = business_days_between(mod_time, today)

            if biz_days >= threshold:
                kva_label = get_kva_category(kva_value, config)
                item = {
                    "record": rec,
                    "days_stalled": biz_days,
                    "kva_category": kva_label,
                    "threshold": threshold,
                    "kva_value": kva_value
                }
                overdue_items.append(item)
                total_count += 1

                # Owner alert
                owner = rec.get("Owner")
                if owner and isinstance(owner, dict):
                    email = owner.get("email", "")
                    if email and email != "null":
                        owner_alerts[email].append({
                            "record": rec,
                            "stage": stage,
                            "days_stalled": biz_days,
                            "threshold": threshold,
                            "kva_category": kva_label
                        })

        if overdue_items:
            stage_results[stage] = overdue_items
            log.info(f"  {stage}: {len(overdue_items)} overdue")

    log.info(f"Total stalled enquiries: {total_count}")
    return stage_results, total_count, owner_alerts


# ============================================================================
# HELPER
# ============================================================================

def _collect_owner_alert(owner_alerts: dict, lead: dict,
                         alert_type: str, days: int):
    """Add a lead alert to the owner's alert list."""
    owner = lead.get("Owner")
    if owner and isinstance(owner, dict):
        email = owner.get("email", "")
        if email and email != "null":
            owner_alerts[email].append({
                "lead": lead,
                "type": alert_type,
                "days": days
            })