"""Resilient HTTP client."""
import time
from typing import Any
import requests

class HttpClient:
    """Small GET-only client with bounded retries and timeouts."""
    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Fetch JSON or raise a descriptive requests exception."""
        error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=15, headers={"User-Agent": "SuperLig-AL/1.0"})
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, ValueError) as exc:
                error = exc
                time.sleep(2**attempt)
        raise requests.RequestException(f"GET failed: {url}") from error
