"""
Zoho OAuth Token Manager
========================
Handles access token generation using the refresh token.
Access tokens expire in 1 hour. This module gets a fresh one each run.
"""

import logging
import sys
import requests

log = logging.getLogger(__name__)


class ZohoAuth:
    """Manages Zoho OAuth2 authentication."""

    def __init__(self, config: dict):
        zoho = config["zoho"]
        self.client_id = zoho["client_id"]
        self.client_secret = zoho["client_secret"]
        self.refresh_token = zoho["refresh_token"]
        self.accounts_url = zoho["accounts_url"]
        self._access_token = None

    def get_access_token(self) -> str:
        """
        Get a valid access token.
        Refreshes automatically using the refresh token.
        """
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
            log.error("Check client_id, client_secret, and refresh_token in config.json")
            sys.exit(1)

    def reset(self):
        """Force a fresh token on next call."""
        self._access_token = None
