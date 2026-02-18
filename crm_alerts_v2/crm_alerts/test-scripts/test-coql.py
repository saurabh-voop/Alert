"""Quick test: which 3-condition WHERE works in COQL?"""
import json, requests

with open("config.json") as f:
    config = json.load(f)

resp = requests.post(f"{config['zoho']['accounts_url']}/oauth/v2/token", data={
    "grant_type": "refresh_token", "client_id": config["zoho"]["client_id"],
    "client_secret": config["zoho"]["client_secret"], "refresh_token": config["zoho"]["refresh_token"]
}, timeout=30)
token = resp.json()["access_token"]
headers = {"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json"}
api = config["zoho"]["api_domain"]

def test(label, query):
    r = requests.post(f"{api}/crm/v5/coql", headers=headers, json={"select_query": query}, timeout=30)
    if r.status_code == 200:
        cnt = len(r.json().get("data", []))
        print(f"  {label:50s} → OK ({cnt} records)")
    else:
        err = r.json().get("message", r.text[:100])
        print(f"  {label:50s} → FAIL: {err}")

print("Testing COQL WHERE syntax for Deals:\n")

# Test 1: Two conditions (this works)
test("2 conditions (Stage + Modified_Time)",
     "SELECT Deal_Name FROM Deals WHERE Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' LIMIT 3")

# Test 2: Three conditions with >=
test("3 conditions with >=",
     "SELECT Deal_Name FROM Deals WHERE Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' and Created_Time >= '2025-04-01T00:00:00+05:30' LIMIT 3")

# Test 3: Three conditions with >
test("3 conditions with >",
     "SELECT Deal_Name FROM Deals WHERE Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' and Created_Time > '2025-03-31T23:59:59+05:30' LIMIT 3")

# Test 4: Three conditions with parentheses
test("3 conditions with parens",
     "SELECT Deal_Name FROM Deals WHERE (Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' and Created_Time > '2025-03-31T23:59:59+05:30') LIMIT 3")

# Test 5: Three conditions, different order
test("3 conditions, Created first",
     "SELECT Deal_Name FROM Deals WHERE Created_Time > '2025-03-31T23:59:59+05:30' and Stage = 'QUOTED' and Modified_Time < '2026-02-16T23:59:59+05:30' LIMIT 3")

# Test 6: Simplified — just Created + Stage
test("2 conditions (Stage + Created >)",
     "SELECT Deal_Name FROM Deals WHERE Stage = 'QUOTED' and Created_Time > '2025-03-31T23:59:59+05:30' LIMIT 3")

# Test 7: between for Created_Time
test("between syntax",
     "SELECT Deal_Name FROM Deals WHERE Stage = 'QUOTED' and Created_Time between '2025-04-01T00:00:00+05:30' and '2026-12-31T23:59:59+05:30' LIMIT 3")

print("\nDone.")