"""
DEBUG v2 — Fixed COQL queries (WHERE clause required)
======================================================
Usage: python debug_crm_v2.py
"""

import json, os, sys, requests

config_path = "config.json"
if not os.path.exists(config_path):
    print(f"ERROR: {config_path} not found"); sys.exit(1)
with open(config_path) as f:
    config = json.load(f)

# --- Token ---
print("=" * 60)
print("Getting access token...")
resp = requests.post(f"{config['zoho']['accounts_url']}/oauth/v2/token", data={
    "grant_type": "refresh_token",
    "client_id": config["zoho"]["client_id"],
    "client_secret": config["zoho"]["client_secret"],
    "refresh_token": config["zoho"]["refresh_token"]
}, timeout=30)
token_data = resp.json()
if "access_token" not in token_data:
    print(f"TOKEN FAILED: {token_data}"); sys.exit(1)
token = token_data["access_token"]
print("Token OK.\n")

headers_coql = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
headers_get = {"Authorization": f"Zoho-oauthtoken {token}"}
api = config["zoho"]["api_domain"]
module = config["zoho"]["enquiry_module"]


def coql(query):
    """Run COQL query and return (status_code, data_or_error)."""
    resp = requests.post(f"{api}/crm/v5/coql", headers=headers_coql,
                         json={"select_query": query}, timeout=30)
    if resp.status_code == 200:
        return 200, resp.json().get("data", [])
    return resp.status_code, resp.text[:300]


# ============================================================================
# TEST 1: COQL Lead fields (with WHERE clause)
# ============================================================================
print("=" * 60)
print("TEST 1: Which Lead fields work in COQL?")
print("=" * 60)

lead_fields_to_test = [
    "id", "Last_Name", "First_Name", "Company", "Phone", "Email",
    "Owner", "Created_Time", "Modified_Time", "Last_Activity_Time",
    "Last_Visited_Time", "Created_By", "Status", "Lead_Source",
    "Lead_Num", "Full_Name"
]

for field in lead_fields_to_test:
    query = f"SELECT id, {field} FROM Leads WHERE id is not null LIMIT 1"
    code, result = coql(query)
    if code == 200 and result:
        val = result[0].get(field, "<<not returned>>")
        if isinstance(val, dict):
            val = json.dumps(val)
        val_str = str(val)[:80]
        print(f"  {field:30s} → OK     Value: {val_str}")
    elif code == 200:
        print(f"  {field:30s} → OK     (no records)")
    else:
        err = ""
        try:
            err = json.loads(result).get("details", {}).get("column_name", "")
            if not err:
                err = json.loads(result).get("message", "")[:60]
        except:
            err = str(result)[:60]
        print(f"  {field:30s} → FAIL   {err}")

# Test $converted separately
print("\n  --- Testing $converted and Converted ---")
for field_test in ["$converted", "Converted"]:
    query = f"SELECT id, Last_Name FROM Leads WHERE id is not null LIMIT 1"
    # Can't select $ fields, but can we filter?
    # Test filter instead
    pass

# Test filtering by Lead_Status
print("\n  --- Can we FILTER by Lead_Status? ---")
query = "SELECT id, Last_Name, Status FROM Leads WHERE Status is not null LIMIT 3"
code, result = coql(query)
if code == 200 and result:
    for r in result:
        print(f"    Lead: {r.get('Last_Name','?')} | Status: {r.get('Status','?')}")
else:
    print(f"    FAIL: {result[:200] if isinstance(result, str) else result}")


# ============================================================================
# TEST 2: COQL Deal/Enquiry fields (with WHERE clause)
# ============================================================================
print("\n" + "=" * 60)
print(f"TEST 2: Which {module} fields work in COQL?")
print("=" * 60)

deal_fields_to_test = [
    "id", "Deal_Name", "Stage", "Amount", "DG_KVA", "Owner",
    "Created_Time", "Modified_Time", "Closing_Date",
    "Account_Name", "Status_Remarks", "Remark_Status",
    "OFFERING", "SEGMENT", "PRIORITY", "ENGINE", "ALTERNATOR",
    "ENQ_NUM", "ENQ_OWNER", "QTY", "MKT", "NATURE", "Type",
    "Description", "Lead_Source", "Contact_Name", "Created_By"
]

for field in deal_fields_to_test:
    query = f"SELECT id, {field} FROM {module} WHERE id is not null LIMIT 1"
    code, result = coql(query)
    if code == 200 and result:
        val = result[0].get(field, "<<not returned>>")
        if isinstance(val, dict):
            val = json.dumps(val)
        val_str = str(val)[:80]
        print(f"  {field:30s} → OK     Value: {val_str}")
    elif code == 200:
        print(f"  {field:30s} → OK     (no records)")
    else:
        err = ""
        try:
            err = json.loads(result).get("details", {}).get("column_name", "")
            if not err:
                err = json.loads(result).get("message", "")[:60]
        except:
            err = str(result)[:60]
        print(f"  {field:30s} → FAIL   {err}")


# ============================================================================
# TEST 3: COQL Owner — what exactly does it return?
# ============================================================================
print("\n" + "=" * 60)
print("TEST 3: What does COQL return for Owner field?")
print("=" * 60)

query = f"SELECT id, Deal_Name, Owner FROM {module} WHERE id is not null LIMIT 3"
code, result = coql(query)
if code == 200 and result:
    for r in result:
        owner = r.get("Owner")
        print(f"  Deal: {r.get('Deal_Name','?')[:40]}")
        print(f"    Owner type: {type(owner).__name__}")
        print(f"    Owner value: {json.dumps(owner)}")
        print()
else:
    print(f"  FAIL: {result[:200] if isinstance(result, str) else result}")


# ============================================================================
# TEST 4: COQL Account_Name — nested or flat?
# ============================================================================
print("=" * 60)
print("TEST 4: What does COQL return for Account_Name?")
print("=" * 60)

query = f"SELECT id, Deal_Name, Account_Name FROM {module} WHERE id is not null LIMIT 3"
code, result = coql(query)
if code == 200 and result:
    for r in result:
        acct = r.get("Account_Name")
        print(f"  Deal: {r.get('Deal_Name','?')[:40]}")
        print(f"    Account_Name type: {type(acct).__name__}")
        print(f"    Account_Name value: {json.dumps(acct)}")
        print()
else:
    print(f"  FAIL: {result[:200] if isinstance(result, str) else result}")


# ============================================================================
# TEST 5: Full Lead query (what the script will use)
# ============================================================================
print("=" * 60)
print("TEST 5: Full Lead query (script simulation)")
print("=" * 60)

query = "SELECT id, Last_Name, Company, Phone, Owner, Created_Time, Last_Activity_Time FROM Leads WHERE Created_Time < '2026-02-15T23:59:59+05:30' LIMIT 3"
code, result = coql(query)
if code == 200:
    print(f"  Returned {len(result)} leads")
    if result:
        r = result[0]
        print(f"  Sample: {r.get('Last_Name','')} | Company: {r.get('Company','')}")
        print(f"  Owner: {json.dumps(r.get('Owner'))}")
        print(f"  Created: {r.get('Created_Time','')} | LastActivity: {r.get('Last_Activity_Time','')}")
else:
    print(f"  FAIL: {result[:300] if isinstance(result, str) else result}")


# ============================================================================
# TEST 6: Full Enquiry query (what the script will use)
# ============================================================================
print("\n" + "=" * 60)
print("TEST 6: Full Enquiry query (script simulation)")
print("=" * 60)

query = f"SELECT id, Deal_Name, Stage, Amount, DG_KVA, Owner, Modified_Time, Closing_Date, Status_Remarks, Account_Name, OFFERING FROM {module} WHERE Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' LIMIT 3"
code, result = coql(query)
if code == 200:
    print(f"  Returned {len(result)} enquiries")
    for r in result[:3]:
        print(f"  Name: {r.get('Deal_Name','')[:50]}")
        print(f"    Stage: {r.get('Stage','')} | DG_KVA: {r.get('DG_KVA','')} | Amount: {r.get('Amount','')}")
        print(f"    Owner: {json.dumps(r.get('Owner'))}")
        print(f"    Account: {json.dumps(r.get('Account_Name'))}")
        print(f"    OFFERING: {r.get('OFFERING','')} | Remarks: {r.get('Status_Remarks','')[:50]}")
        print()
else:
    print(f"  FAIL: {result[:300] if isinstance(result, str) else result}")


# ============================================================================
# TEST 7: Users API (check if scope works)
# ============================================================================
print("=" * 60)
print("TEST 7: Users API")
print("=" * 60)

resp = requests.get(f"{api}/crm/v2/users?type=AllUsers", headers=headers_get, timeout=30)
if resp.status_code == 200:
    users = resp.json().get("users", [])
    print(f"  Users found: {len(users)}")
    for u in users[:5]:
        print(f"    {u.get('id','')} → {u.get('full_name','')} ({u.get('email','')})")
elif resp.status_code == 401:
    print(f"  SCOPE MISSING — You need to add ZohoCRM.users.READ to your scope")
    print(f"  BUT — Owner from COQL might already have name (check TEST 3 above)")
    print(f"  If TEST 3 shows name, we DON'T need Users API at all!")
else:
    print(f"  Error: {resp.status_code} — {resp.text[:200]}")


print("\n" + "=" * 60)
print("DEBUG v2 COMPLETE — Share full output")
print("=" * 60)