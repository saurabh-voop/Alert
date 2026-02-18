"""
DEBUG SCRIPT — Run this to see exactly what Zoho CRM returns
==============================================================
This will:
1. Fetch 1 Lead record and print ALL its fields
2. Fetch 1 Enquiry (Deal) record and print ALL its fields
3. Fetch all CRM users and print their ID → name mapping
4. Show what the Owner field actually looks like

Usage: python debug_crm.py
"""

import json
import os
import sys
import requests

# Load config
config_path = "config.json"
if not os.path.exists(config_path):
    print(f"ERROR: {config_path} not found"); sys.exit(1)
with open(config_path) as f:
    config = json.load(f)

# Get access token
print("=" * 60)
print("STEP 1: Getting access token...")
print("=" * 60)
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
print("Token obtained.\n")

headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
api = config["zoho"]["api_domain"]


# ============================================================================
# STEP 2: Fetch 1 Lead — see ALL fields
# ============================================================================
print("=" * 60)
print("STEP 2: Fetching 1 Lead record (ALL fields via GET API)...")
print("=" * 60)

resp = requests.get(f"{api}/crm/v2/Leads?per_page=1", headers=headers, timeout=30)
if resp.status_code == 200:
    leads = resp.json().get("data", [])
    if leads:
        lead = leads[0]
        print(f"\nTotal fields in Lead record: {len(lead)}")
        print("-" * 60)
        for key, val in sorted(lead.items()):
            val_str = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
            if len(val_str) > 100: val_str = val_str[:100] + "..."
            print(f"  {key:30s} = {val_str}")
        
        print("\n--- OWNER FIELD (detailed) ---")
        owner = lead.get("Owner")
        print(f"  Type: {type(owner).__name__}")
        print(f"  Value: {json.dumps(owner, indent=2)}")
        
        print("\n--- KEY FIELDS CHECK ---")
        for f in ["Last_Name","Company","Phone","Created_Time","Modified_Time",
                   "Last_Activity_Time","Last_Visited_Time","Converted","Lead_Status","Created_By"]:
            val = lead.get(f, "<<MISSING>>")
            if isinstance(val, dict): val = json.dumps(val)
            print(f"  {f:30s} = {val}")
    else:
        print("  No leads found.")
else:
    print(f"  API error: {resp.status_code} — {resp.text[:200]}")


# ============================================================================
# STEP 3: Fetch 1 Lead via COQL — see what COQL returns
# ============================================================================
print("\n" + "=" * 60)
print("STEP 3: Fetching 1 Lead via COQL...")
print("=" * 60)

coql = "SELECT id, Last_Name, Company, Phone, Owner, Created_Time, Modified_Time, Last_Activity_Time, Last_Visited_Time, Created_By FROM Leads LIMIT 1"
resp = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": coql}, timeout=30)
if resp.status_code == 200:
    data = resp.json().get("data", [])
    if data:
        rec = data[0]
        print(f"\nCOQL Lead fields returned: {len(rec)}")
        for key, val in sorted(rec.items()):
            val_str = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
            print(f"  {key:30s} = {val_str}")
        print("\n--- OWNER via COQL ---")
        print(f"  Type: {type(rec.get('Owner')).__name__}")
        print(f"  Value: {json.dumps(rec.get('Owner'), indent=2)}")
else:
    print(f"  COQL error: {resp.status_code} — {resp.text[:300]}")


# ============================================================================
# STEP 4: Fetch 1 Enquiry (Deal) — ALL fields
# ============================================================================
print("\n" + "=" * 60)
print("STEP 4: Fetching 1 Enquiry/Deal record (ALL fields)...")
print("=" * 60)

module = config["zoho"]["enquiry_module"]
resp = requests.get(f"{api}/crm/v2/{module}?per_page=1", headers=headers, timeout=30)
if resp.status_code == 200:
    deals = resp.json().get("data", [])
    if deals:
        deal = deals[0]
        print(f"\nTotal fields in {module} record: {len(deal)}")
        print("-" * 60)
        for key, val in sorted(deal.items()):
            val_str = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
            if len(val_str) > 100: val_str = val_str[:100] + "..."
            print(f"  {key:30s} = {val_str}")

        print("\n--- OWNER FIELD (detailed) ---")
        owner = deal.get("Owner")
        print(f"  Type: {type(owner).__name__}")
        print(f"  Value: {json.dumps(owner, indent=2)}")

        print("\n--- KEY FIELDS CHECK ---")
        for f in ["Deal_Name","Stage","Amount","DG_KVA","Account_Name","Remark_Status",
                   "Created_Time","Modified_Time","Closing_Date","OFFERING","Owner","Created_By"]:
            val = deal.get(f, "<<MISSING>>")
            if isinstance(val, dict): val = json.dumps(val)
            print(f"  {f:30s} = {val}")
    else:
        print(f"  No {module} records found.")
else:
    print(f"  API error: {resp.status_code} — {resp.text[:200]}")


# ============================================================================
# STEP 5: Fetch 1 Enquiry via COQL
# ============================================================================
print("\n" + "=" * 60)
print("STEP 5: Fetching 1 Enquiry via COQL...")
print("=" * 60)

coql = f"SELECT id, Deal_Name, Stage, Amount, DG_KVA, Owner, Modified_Time, Closing_Date, Remark_Status FROM {module} LIMIT 1"
resp = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": coql}, timeout=30)
if resp.status_code == 200:
    data = resp.json().get("data", [])
    if data:
        rec = data[0]
        print(f"\nCOQL {module} fields returned: {len(rec)}")
        for key, val in sorted(rec.items()):
            val_str = json.dumps(val) if isinstance(val, (dict, list)) else str(val)
            print(f"  {key:30s} = {val_str}")
        print("\n--- OWNER via COQL ---")
        print(f"  Type: {type(rec.get('Owner')).__name__}")
        print(f"  Value: {json.dumps(rec.get('Owner'), indent=2)}")
else:
    print(f"  COQL error: {resp.status_code} — {resp.text[:300]}")


# ============================================================================
# STEP 6: Test COQL fields one by one for Leads
# ============================================================================
print("\n" + "=" * 60)
print("STEP 6: Testing individual COQL fields for Leads...")
print("=" * 60)

test_fields = ["Converted", "Lead_Status", "Last_Activity_Time", "Last_Visited_Time", "Created_By"]
for field in test_fields:
    coql = f"SELECT id, {field} FROM Leads LIMIT 1"
    resp = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": coql}, timeout=30)
    status = "OK" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
    detail = ""
    if resp.status_code != 200:
        try:
            detail = resp.json().get("message", "")[:80]
        except:
            detail = resp.text[:80]
    print(f"  {field:30s} → {status}  {detail}")


# ============================================================================
# STEP 7: Test COQL fields one by one for Deals
# ============================================================================
print("\n" + "=" * 60)
print("STEP 7: Testing individual COQL fields for Deals...")
print("=" * 60)

test_fields_deals = ["Account_Name", "Remark_Status", "OFFERING", "DG_KVA", "Closing_Date", "Stage"]
for field in test_fields_deals:
    coql = f"SELECT id, {field} FROM {module} LIMIT 1"
    resp = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": coql}, timeout=30)
    status = "OK" if resp.status_code == 200 else f"FAIL ({resp.status_code})"
    detail = ""
    if resp.status_code != 200:
        try:
            detail = resp.json().get("message", "")[:80]
        except:
            detail = resp.text[:80]
    print(f"  {field:30s} → {status}  {detail}")


# ============================================================================
# STEP 8: Fetch CRM Users
# ============================================================================
print("\n" + "=" * 60)
print("STEP 8: Fetching CRM users (for Owner ID → Name mapping)...")
print("=" * 60)

resp = requests.get(f"{api}/crm/v2/users?type=AllUsers", 
                    headers={"Authorization": f"Zoho-oauthtoken {token}"}, timeout=30)
if resp.status_code == 200:
    users = resp.json().get("users", [])
    print(f"\nTotal users: {len(users)}")
    print(f"{'ID':20s} {'Name':25s} {'Email':35s}")
    print("-" * 80)
    for u in users[:20]:  # Show first 20
        uid = str(u.get("id", ""))
        name = u.get("full_name", "")
        email = u.get("email", "")
        print(f"  {uid:20s} {name:25s} {email:35s}")
    if len(users) > 20:
        print(f"  ... and {len(users) - 20} more users")
else:
    print(f"  Users API error: {resp.status_code} — {resp.text[:200]}")


print("\n" + "=" * 60)
print("DEBUG COMPLETE")
print("=" * 60)
print("\nCopy-paste the FULL output above and share it.")
print("This will tell us:")
print("  1. Which fields exist and which don't")
print("  2. What Owner looks like (ID vs name)")
print("  3. Which COQL fields work and which fail")
print("  4. User ID → Name mapping for owner resolution")