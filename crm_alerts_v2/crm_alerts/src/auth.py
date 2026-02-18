"""
Zoho OAuth Token Manager
"""

import logging
import sys
import requests

log = logging.getLogger(__name__)


class ZohoAuth:

    def __init__(self, config: dict):
        zoho = config["zoho"]
        self.client_id = zoho["client_id"]
        self.client_secret = zoho["client_secret"]
        self.refresh_token = zoho["refresh_token"]
        self.accounts_url = zoho["accounts_url"]
        self._access_token = None

    def get_access_token(self) -> str:
        if self._access_token:
            return self._access_token

        url = f"{self.accounts_url}/oauth/v2/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token
        }

        try:
            resp = requests.post(url, data=payload, timeout=30)
            result = resp.json()
        except requests.RequestException as e:
            log.error(f"Network error during token refresh: {e}")
            sys.exit(1)

        if "access_token" in result:
            self._access_token = result["access_token"]
            log.info("Zoho access token obtained successfully.")
            return self._access_token
        else:
            log.error(f"Token refresh failed: {result}")
            sys.exit(1)
