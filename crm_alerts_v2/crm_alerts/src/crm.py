"""
Zoho CRM API Client
====================
Uses COQL for queries. Bulk user + account lookup for name resolution.
"""

import logging
import requests

log = logging.getLogger(__name__)


class ZohoCRM:

    def __init__(self, auth, config: dict):
        self.auth = auth
        self.api_domain = config["zoho"]["api_domain"]
        self.enquiry_module = config["zoho"]["enquiry_module"]
        self._user_cache = {}
        self._account_cache = {}

    def _headers_json(self) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {self.auth.get_access_token()}",
            "Content-Type": "application/json"
        }

    def _headers_get(self) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {self.auth.get_access_token()}"
        }

    # ----------------------------------------------------------------
    # COQL
    # ----------------------------------------------------------------

    def coql_query(self, query: str) -> list:
        url = f"{self.api_domain}/crm/v5/coql"
        try:
            resp = requests.post(url, headers=self._headers_json(),
                                 json={"select_query": query}, timeout=30)
        except requests.RequestException as e:
            log.warning(f"Network error: {e}")
            return []
        if resp.status_code == 200:
            return resp.json().get("data", [])
        elif resp.status_code == 204:
            return []
        else:
            log.warning(f"COQL error ({resp.status_code}): {resp.text[:300]}")
            return []

    def fetch_records(self, module: str, fields: list, where: str,
                      max_records: int = 1000) -> list:
        fields_str = ", ".join(fields)
        all_records = []
        offset = 0
        while offset < max_records:
            query = (
                f"SELECT {fields_str} FROM {module} "
                f"WHERE {where} "
                f"LIMIT 200 OFFSET {offset}"
            )
            records = self.coql_query(query)
            if not records:
                break
            all_records.extend(records)
            if len(records) < 200:
                break
            offset += 200
        return all_records

    # ----------------------------------------------------------------
    # USER LOOKUP
    # ----------------------------------------------------------------

    def fetch_users(self) -> dict:
        if self._user_cache:
            return self._user_cache
        url = f"{self.api_domain}/crm/v2/users?type=AllUsers"
        try:
            resp = requests.get(url, headers=self._headers_get(), timeout=30)
            if resp.status_code == 200:
                for u in resp.json().get("users", []):
                    uid = str(u.get("id", ""))
                    name = u.get("full_name", "")
                    if not name:
                        name = (u.get("first_name", "") + " " + u.get("last_name", "")).strip()
                    self._user_cache[uid] = {"name": name, "email": u.get("email", "")}
                log.info(f"Fetched {len(self._user_cache)} CRM users.")
            else:
                log.warning(f"Users API error ({resp.status_code}): {resp.text[:200]}")
        except Exception as e:
            log.warning(f"Could not fetch users: {e}")
        return self._user_cache

    # ----------------------------------------------------------------
    # ACCOUNT LOOKUP — GET API with caching
    # ----------------------------------------------------------------

    def bulk_fetch_accounts(self, records: list):
        """
        Pre-fetch account names. Uses GET /Accounts/{id} per unique ID.
        Caches results so each account is fetched only once.
        With 2000 unique accounts this takes ~3-4 min (vs 30+ min without caching).
        """
        account_ids = set()
        for rec in records:
            acct = rec.get("Account_Name")
            if isinstance(acct, dict):
                aid = str(acct.get("id", ""))
                if aid and aid not in self._account_cache:
                    account_ids.add(aid)

        if not account_ids:
            log.info("  No new accounts to fetch.")
            return

        total = len(account_ids)
        log.info(f"  Fetching {total} unique account names (this may take 2-4 min)...")
        fetched = 0
        failed = 0

        for aid in account_ids:
            url = f"{self.api_domain}/crm/v2/Accounts/{aid}"
            try:
                resp = requests.get(url, headers=self._headers_get(), timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        self._account_cache[aid] = str(data[0].get("Account_Name", aid))
                        fetched += 1
                    else:
                        self._account_cache[aid] = "-"
                        failed += 1
                else:
                    self._account_cache[aid] = "-"
                    failed += 1
            except:
                self._account_cache[aid] = "-"
                failed += 1

            done = fetched + failed
            if done % 200 == 0:
                log.info(f"    Progress: {done}/{total} accounts")

        log.info(f"  Done: {fetched} resolved, {failed} failed, {len(self._account_cache)} cached.")

    def get_account_name(self, account_id: str) -> str:
        if not account_id:
            return "-"
        return self._account_cache.get(account_id, account_id)