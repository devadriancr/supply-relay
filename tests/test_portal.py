import hashlib
import hmac
import json

import httpx
import pytest

from relay.portal import PortalClient, PortalError


def test_requests_are_signed_with_the_shared_key(settings):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        return httpx.Response(200, json={"sync_run": 1, "rows": 2})

    with PortalClient(settings, transport=httpx.MockTransport(handler)) as portal:
        assert portal.send_vendor(400191, {"vendor": {"name": "AÑO"}}) == {"sync_run": 1, "rows": 2}

    request = seen["request"]
    body = request.content
    timestamp = request.headers["X-Sync-Timestamp"]
    expected = hmac.new(b"k" * 64, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()

    assert str(request.url) == "https://portal.test/api/sync/vendors/400191"
    assert request.headers["X-Sync-Signature"] == expected
    assert json.loads(body) == {"vendor": {"name": "AÑO"}}


def test_portal_errors_explain_what_failed(settings):
    def handler(request):
        return httpx.Response(422, json={"message": "invalid", "errors": {"part_numbers.0.number": ["Too long."]}})

    with PortalClient(settings, transport=httpx.MockTransport(handler)) as portal:
        with pytest.raises(PortalError, match="422: Too long."):
            portal.send_work_calendars([])


def test_redirects_are_not_followed(settings):
    def handler(request):
        return httpx.Response(302, headers={"Location": "http://elsewhere.test/"})

    with PortalClient(settings, transport=httpx.MockTransport(handler)) as portal:
        with pytest.raises(PortalError, match="302"):
            portal.send_work_calendars([])
