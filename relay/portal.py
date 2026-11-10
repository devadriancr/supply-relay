"""Sends data to the supplier portal. Every request is signed with the shared
key (SYNC_KEY) so the portal can reject anything that does not come from here.

Signature: hex HMAC-SHA256 of "{unix timestamp}.{raw body}", sent in the
X-Sync-Timestamp and X-Sync-Signature headers. The portal checks it in
app/Http/Middleware/VerifySyncSignature.php.
"""

import hashlib
import hmac
import json
import time

import httpx

from relay.config import Settings


class PortalError(Exception):
    pass


def sign(key: str, timestamp: str, body: bytes) -> str:
    return hmac.new(key.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


class PortalClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._key = settings.sync_key.get_secret_value()
        self._client = httpx.Client(
            base_url=settings.portal_base,
            timeout=settings.portal_timeout,
            verify=settings.portal_verify_tls,
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "supply-relay"},
        )

    def __enter__(self) -> "PortalClient":
        return self

    def __exit__(self, *exc) -> None:
        self._client.close()

    def send_vendor(self, vendor: int, snapshot: dict) -> dict:
        return self._post(f"/api/sync/vendors/{int(vendor)}", snapshot)

    def send_work_calendars(self, calendars: list[dict]) -> dict:
        return self._post("/api/sync/work-calendars", {"calendars": calendars})

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        timestamp = str(int(time.time()))
        response = self._client.post(
            path,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Sync-Timestamp": timestamp,
                "X-Sync-Signature": sign(self._key, timestamp, body),
            },
        )
        if response.is_success:
            return response.json()
        raise PortalError(f"El portal respondió {response.status_code}: {self._reason(response)}")

    @staticmethod
    def _reason(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.reason_phrase
        errors = data.get("errors") or {}
        first_error = next(iter(errors.values()), [None])[0]
        return str(first_error or data.get("message") or response.reason_phrase)[:300]
