"""Quick check: what dates are the enquiries showing?"""
import json, requests

with open("config.json") as f:
    config = json.load(f)

# Check config
print("=== CONFIG CHECK ===")
print(f"send_owner_alerts: {config['email']['send_owner_alerts']}")
print(f"summary_recipients: {config['email']['summary_recipients']}")
print(f"enquiry_cutoff_date: {config.get('enquiry_cutoff_date', 'NOT SET')}")
print()

# Token
resp = requests.post(f"{config['zoho']['accounts_url']}/oauth/v2/token", data={
    "grant_type": "refresh_token", "client_id": config["zoho"]["client_id"],
    "client_secret": config["zoho"]["client_secret"], "refresh_token": config["zoho"]["refresh_token"]
}, timeout=30)
token = resp.json()["access_token"]
headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
api = config["zoho"]["api_domain"]

# Fetch 5 QUOTED enquiries with the actual query
query = "SELECT Deal_Name, Created_Time, Modified_Time, Stage FROM Deals WHERE Stage = 'QUOTED' and Created_Time > '2025-04-01T00:00:00+05:30' LIMIT 5"
resp = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": query}, timeout=30)

if resp.status_code == 200:
    data = resp.json().get("data", [])
    print(f"=== SAMPLE QUOTED ENQUIRIES (Created after 2025-04-01) ===")
    print(f"Total returned: {len(data)}")
    for r in data:
        print(f"  {r.get('Deal_Name','?')[:50]}")
        print(f"    Created:  {r.get('Created_Time','?')}")
        print(f"    Modified: {r.get('Modified_Time','?')}")
        print()
else:
    print(f"COQL error: {resp.text[:200]}")

# Now check: are there records with Modified_Time before April 2025?
query2 = "SELECT Deal_Name, Created_Time, Modified_Time FROM Deals WHERE Stage = 'QUOTED' and Created_Time > '2025-04-01T00:00:00+05:30' LIMIT 200"
resp2 = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": query2}, timeout=30)

if resp2.status_code == 200:
    data2 = resp2.json().get("data", [])
    old_mod = [r for r in data2 if r.get("Modified_Time","") < "2025-04-01"]
    print(f"=== DATE CHECK ===")
    print(f"Total fetched: {len(data2)}")
    print(f"Modified BEFORE 2025-04-01: {len(old_mod)}")
    if old_mod:
        print("Examples of old Modified_Time:")
        for r in old_mod[:3]:
            print(f"  {r.get('Deal_Name','?')[:50]} | Created: {r.get('Created_Time','')} | Modified: {r.get('Modified_Time','')}")