"""
Zoho CRM API Client
====================
Handles all API calls to Zoho CRM.
Uses COQL (CRM Object Query Language) which supports ALL fields
including Modified_Time and Created_Time.
"""

import logging
import requests

log = logging.getLogger(__name__)


class ZohoCRM:
    """Zoho CRM API wrapper using COQL queries."""

    def __init__(self, auth, config: dict):
        self.auth = auth
        self.api_domain = config["zoho"]["api_domain"]
        self.enquiry_module = config["zoho"]["enquiry_module"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Zoho-oauthtoken {self.auth.get_access_token()}",
            "Content-Type": "application/json"
        }

    def coql_query(self, query: str) -> list:
        """
        Execute a COQL query.
        COQL supports all fields including Modified_Time, Created_Time.

        Args:
            query: Full COQL SELECT query string

        Returns:
            List of record dicts
        """
        url = f"{self.api_domain}/crm/v5/coql"
        payload = {"select_query": query}

        try:
            resp = requests.post(url, headers=self._headers(),
                                 json=payload, timeout=30)
        except requests.RequestException as e:
            log.warning(f"Network error during COQL query: {e}")
            return []

        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", [])
        elif resp.status_code == 204:
            return []
        else:
            log.warning(f"COQL error ({resp.status_code}): {resp.text[:300]}")
            return []

    def fetch_records(self, module: str, fields: list, where: str,
                      max_records: int = 1000) -> list:
        """
        Fetch records using COQL with automatic pagination.

        Args:
            module: Module API name (Leads, Deals)
            fields: List of field API names to SELECT
            where: WHERE clause (without the WHERE keyword)
            max_records: Max records to fetch

        Returns:
            List of record dicts
        """
        fields_str = ", ".join(fields)
        all_records = []
        offset = 0
        page_size = 200

        while offset < max_records:
            query = (
                f"SELECT {fields_str} FROM {module} "
                f"WHERE {where} "
                f"LIMIT {page_size} OFFSET {offset}"
            )

            records = self.coql_query(query)
            if not records:
                break

            all_records.extend(records)
            log.debug(f"  COQL {module} offset {offset}: {len(records)} records")

            if len(records) < page_size:
                break

            offset += page_size

        return all_records