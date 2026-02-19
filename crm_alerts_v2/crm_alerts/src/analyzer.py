"""
Overdue Analyzer
=================
Core business logic.
"""

import logging
from datetime import date, datetime, timedelta
from collections import defaultdict

log = logging.getLogger(__name__)


# ============================================================================
# BUSINESS DAY CALCULATOR
# ============================================================================

def business_days_between(start, end=None) -> int:
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
# OWNER + ACCOUNT RESOLVERS
# ============================================================================

def resolve_owner(record: dict, user_cache: dict) -> tuple:
    owner = record.get("Owner")
    if owner is None:
        return "-", ""
    if isinstance(owner, dict):
        if owner.get("name") and str(owner.get("name")) != "null":
            return owner["name"], owner.get("email", "")
        uid = str(owner.get("id", ""))
        user = user_cache.get(uid, {})
        return user.get("name", uid), user.get("email", "")
    uid = str(owner)
    user = user_cache.get(uid, {})
    return user.get("name", uid), user.get("email", "")


def resolve_account(record: dict, crm) -> str:
    acct = record.get("Account_Name")
    if acct is None:
        return "-"
    if isinstance(acct, dict):
        if acct.get("name") and str(acct.get("name")) != "null":
            return acct["name"]
        aid = str(acct.get("id", ""))
        if aid:
            return crm.get_account_name(aid)
    return str(acct) if acct else "-"


# ============================================================================
# FIELD VALUE EXTRACTOR
# ============================================================================

def get_field_value(record: dict, field_name: str,
                    user_cache: dict = None, crm=None) -> str:
    if user_cache is None:
        user_cache = {}

    # Lead Full Name (First + Last)
    if field_name == "Full_Name":
        first = record.get("First_Name", "")
        last = record.get("Last_Name", "")
        if first and str(first) not in ("null", "None"):
            return f"{first} {last}".strip()
        return str(last) if last else "-"

    # DG_KVA — show NA instead of -
    if field_name == "DG_KVA":
        val = record.get("DG_KVA")
        if val is None or str(val) in ("null", "None", ""):
            return "NA"
        return str(val)

    # Owner
    if field_name == "Owner.name" or field_name == "Owner":
        name, _ = resolve_owner(record, user_cache)
        return name
    if field_name == "Owner.email":
        _, email = resolve_owner(record, user_cache)
        return email if email else "-"

    # Account_Name
    if field_name == "Account_Name":
        if crm:
            return resolve_account(record, crm)
        acct = record.get("Account_Name")
        if isinstance(acct, dict):
            return acct.get("name", acct.get("id", "-"))
        return str(acct) if acct else "-"

    # Contact_Name
    if field_name == "Contact_Name":
        contact = record.get("Contact_Name")
        if isinstance(contact, dict):
            return contact.get("name", contact.get("id", "-"))
        return str(contact) if contact else "-"

    # Created_By
    if field_name == "Created_By":
        cb = record.get("Created_By")
        if isinstance(cb, dict):
            if cb.get("name"):
                return cb["name"]
            uid = str(cb.get("id", ""))
            user = user_cache.get(uid, {})
            return user.get("name", uid)
        return str(cb) if cb else "-"

    # Generic nested field
    if "." in field_name:
        parts = field_name.split(".")
        parent = record.get(parts[0])
        if parent and isinstance(parent, dict):
            val = parent.get(parts[1])
            if val and str(val) != "null":
                return str(val)
        return "-"

    # Simple field
    val = record.get(field_name)
    if val is None or str(val) == "null" or str(val) == "None":
        return "-"
    return str(val)


# ============================================================================
# THRESHOLD LOGIC
# ============================================================================

def get_kva_value(record: dict) -> int:
    raw = record.get("DG_KVA")
    if raw and str(raw) not in ("null", "None", ""):
        try:
            return int(float(str(raw)))
        except (ValueError, TypeError):
            return 0
    return 0

def get_kva_category(kva_value: int, config: dict) -> str:
    if kva_value == 0:
        return "NA"
    for cat in config["kva_categories"]:
        if cat["min_kva"] <= kva_value <= cat["max_kva"]:
            return cat["label"]
    return config["default_thresholds"]["label"]

def get_threshold_days(stage: str, kva_value: int, config: dict) -> int:
    fixed = config.get("fixed_stage_thresholds", {})
    if stage in fixed:
        return int(fixed[stage])
    stage_key = {"YET_TO_QUOTE": "yet_to_quote_days",
                 "QUOTED": "quoted_days",
                 "FINALIZATION": "finalization_days"}.get(stage)
    if not stage_key:
        return 1
    for cat in config["kva_categories"]:
        if cat["min_kva"] <= kva_value <= cat["max_kva"]:
            return int(cat[stage_key])
    val = config["default_thresholds"].get(stage_key)
    if val is not None:
        try:
            return int(val)
        except (ValueError, TypeError):
            return 1
    return 1


# ============================================================================
# COQL FIELD LISTS (do NOT include "id")
# ============================================================================

LEAD_FIELDS = [
    "Last_Name", "First_Name", "Company", "Phone", "Email",
    "Owner", "Created_Time", "Modified_Time", "Last_Activity_Time",
    "Last_Visited_Time", "Created_By", "Status", "Lead_Source", "Lead_Num"
]

ENQUIRY_FIELDS = [
    "Deal_Name", "Stage", "Amount", "DG_KVA",
    "Owner", "Created_Time", "Modified_Time", "Closing_Date",
    "Status_Remarks", "Account_Name", "OFFERING", "ENQ_NUM"
]


# ============================================================================
# FETCH OVERDUE LEADS
# ============================================================================

def find_overdue_leads(crm, config: dict, user_cache: dict) -> tuple:
    today = date.today()
    action_days = config["lead_thresholds"]["no_action_days"]
    convert_days = config["lead_thresholds"]["not_converted_days"]

    cutoff = today - timedelta(days=action_days + 3)
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    lead_cutoff = config.get("lead_cutoff_date", config.get("enquiry_cutoff_date", "2025-04-01"))
    where = (
        f"Created_Time between '{lead_cutoff}T00:00:00+05:30' "
        f"and '{cutoff_str}T23:59:59+05:30'"
    )

    log.info("Fetching leads (COQL)...")
    leads = crm.fetch_records("Leads", LEAD_FIELDS, where, max_records=2000)
    log.info(f"  Found {len(leads)} leads (broad filter)")

    terminal_statuses = config.get("lead_terminal_statuses",
                                    ["ORDER WON", "Converted", "Junk", "Not Qualified"])
    terminal_set = set(s.lower() for s in terminal_statuses)

    overdue_no_action = []
    overdue_not_converted = []
    owner_alerts = defaultdict(list)

    for lead in leads:
        status = lead.get("Status")
        if status and str(status).lower() in terminal_set:
            continue

        created = lead.get("Created_Time", "")
        if not created:
            continue
        biz_days = business_days_between(created, today)

        last_activity = lead.get("Last_Activity_Time")
        no_activity = (not last_activity or str(last_activity) in ("null", "None"))

        if biz_days >= action_days and no_activity:
            overdue_no_action.append({"lead": lead, "biz_days": biz_days})
            _, owner_email = resolve_owner(lead, user_cache)
            if owner_email:
                owner_alerts[owner_email].append({
                    "lead": lead, "type": "No Action", "days": biz_days
                })

        if biz_days >= convert_days:
            overdue_not_converted.append({"lead": lead, "biz_days": biz_days})
            _, owner_email = resolve_owner(lead, user_cache)
            if owner_email:
                owner_alerts[owner_email].append({
                    "lead": lead, "type": "Not Converted", "days": biz_days
                })

    log.info(f"  After filtering: No action: {len(overdue_no_action)} | Not converted: {len(overdue_not_converted)}")
    return overdue_no_action, overdue_not_converted, owner_alerts


# ============================================================================
# FETCH STALLED ENQUIRIES
# ============================================================================

def find_stalled_enquiries(crm, config: dict, user_cache: dict) -> tuple:
    today = date.today()
    module = config["zoho"]["enquiry_module"]
    terminal = config["terminal_stages"]

    stage_results = {}
    total_count = 0
    owner_alerts = defaultdict(list)

    for stage in config["stages_to_monitor"]:
        if stage in terminal:
            continue

        enq_cutoff = config.get("enquiry_cutoff_date", "2025-04-01")
        where = (
            f"Stage = '{stage}' "
            f"and Created_Time > '{enq_cutoff}T00:00:00+05:30'"
        )

        log.info(f"Fetching enquiries at stage: {stage}...")
        records = crm.fetch_records(module, ENQUIRY_FIELDS, where, max_records=1000)

        cutoff = today - timedelta(days=1)
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

                _, owner_email = resolve_owner(rec, user_cache)
                if owner_email:
                    owner_alerts[owner_email].append({
                        "record": rec,
                        "stage": stage,
                        "days_stalled": biz_days,
                        "threshold": threshold,
                        "kva_category": kva_label
                    })

        if overdue_items:
            stage_results[stage] = overdue_items
            log.info(f"  {stage}: {len(overdue_items)} stalled")

    log.info(f"Total stalled enquiries: {total_count}")
    return stage_results, total_count, owner_alerts