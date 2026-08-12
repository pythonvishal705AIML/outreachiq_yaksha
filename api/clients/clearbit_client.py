import os
import logging
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class ClearbitClient:
    """
    Lightweight client for Clearbit Company API.

    Uses two endpoints:
    - GET https://company.clearbit.com/v1/domains/find?name={company_name}
    - GET https://company.clearbit.com/v2/companies/find?domain={domain}
    """

    BASE_URL = "https://company.clearbit.com"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("CLEARBIT_API_KEY")
        if not self.api_key:
            raise ValueError("CLEARBIT_API_KEY is required for ClearbitClient.")

        self._client = httpx.Client(
            base_url=self.BASE_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=5.0,
        )

    def find_domain_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Returns Clearbit's domain record by company name, or None if not found.
        """
        if not name:
            return None

        try:
            resp = self._client.get(
                "/v1/domains/find",
                params={"name": name},
            )
            if resp.status_code == 404:
                # Not found is a normal outcome
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Clearbit domain lookup failed for '{name}': "
                f"{e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Clearbit domain lookup error for '{name}': {e}", exc_info=True)
        return None

    def find_company_by_domain(self, domain: str) -> Optional[Dict[str, Any]]:
        """
        Returns Clearbit's full company record by domain, or None if not found.
        """
        if not domain:
            return None

        try:
            resp = self._client.get(
                "/v2/companies/find",
                params={"domain": domain},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning(
                f"Clearbit company lookup failed for domain '{domain}': "
                f"{e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            logger.error(f"Clearbit company lookup error for '{domain}': {e}", exc_info=True)
        return None

