"""Deterministic network fixtures. Never packaged in either production image."""

import base64
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx

from steamscope_social.core.database import utcnow
from steamscope_social.modules.auth.openid import NS, PROVIDER

SIGNATURE = base64.b64encode(b"controlled-signature-fixture!!").decode()
DISCOVERY = f"""<?xml version="1.0"?><xrds:XRDS xmlns:xrds="xri://$xrds" xmlns="xri://$xrd*($v*2.0)">
<XRD><Service><Type>{NS}/signon</Type><URI>{PROVIDER}</URI></Service></XRD></xrds:XRDS>"""


def assertion(login_url: str, steam_id: str = "76561198000000001", **overrides) -> dict[str, str]:
    return_to = parse_qs(urlsplit(login_url).query)["openid.return_to"][0]
    params = {
        "state": parse_qs(urlsplit(return_to).query)["state"][0],
        "openid.ns": NS,
        "openid.mode": "id_res",
        "openid.op_endpoint": PROVIDER,
        "openid.claimed_id": f"http://steamcommunity.com/openid/id/{steam_id}",
        "openid.identity": f"http://steamcommunity.com/openid/id/{steam_id}",
        "openid.return_to": return_to,
        "openid.response_nonce": utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") + uuid4().hex,
        "openid.assoc_handle": "fixture-association",
        "openid.signed": "op_endpoint,claimed_id,identity,return_to,response_nonce,assoc_handle",
        "openid.sig": SIGNATURE,
    }
    params.update(overrides)
    return params


class SteamTransport:
    def __init__(self):
        self.calls = []
        self.failure = None
        self.discovery = DISCOVERY
        self.verification = f"ns:{NS}\nis_valid:true\n"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append((request.method, str(request.url)))
        if self.failure == "timeout":
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if request.method == "GET" and str(request.url).startswith(
            "https://steamcommunity.com/openid/id/"
        ):
            return httpx.Response(200, text=self.discovery)
        assert str(request.url) == PROVIDER and request.method == "POST"
        form = parse_qs(request.content.decode())
        assert form["openid.mode"] == ["check_authentication"]
        valid = form.get("openid.sig") == [SIGNATURE]
        return httpx.Response(
            200, text=self.verification if valid else f"ns:{NS}\nis_valid:false\n"
        )
