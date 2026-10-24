"""Steam-only OpenID 2.0 relying party; Steam performs signature verification.

No shared associations or locally implemented OpenID cryptography. Discovery and
check_authentication use fixed HTTPS Steam URLs, never callback-selected targets.
"""

import asyncio
import base64
import binascii
import re
from datetime import timedelta
from urllib.parse import urlencode
from xml.etree import ElementTree

import httpx

from steamscope_social.core.config import Settings
from steamscope_social.core.database import utcnow

NS = "http://specs.openid.net/auth/2.0"
PROVIDER = "https://steamcommunity.com/openid/login"
IDENTIFIER_SELECT = NS + "/identifier_select"
CLAIM = re.compile(r"^https?://steamcommunity\.com/openid/id/([0-9]{17})$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
SIGNED = {"op_endpoint", "return_to", "response_nonce", "assoc_handle", "claimed_id", "identity"}


class OpenIDRejected(Exception):
    """Safe error category; never include provider bodies or assertion parameters."""


def callback_parameters(pairs: list[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    if len(pairs) > 30:
        raise OpenIDRejected()
    for key, value in pairs:
        if key in result or len(key) > 80 or len(value) > 2048:
            raise OpenIDRejected()
        if key != "state" and not re.fullmatch(r"openid\.[a-zA-Z0-9_.]+", key):
            raise OpenIDRejected()
        result[key] = value
    if not TOKEN.fullmatch(result.get("state", "")):
        raise OpenIDRejected()
    return result


def return_url(config: Settings, state: str) -> str:
    return config.callback_url + "?" + urlencode({"state": state})


def authentication_url(config: Settings, state: str) -> str:
    return (
        PROVIDER
        + "?"
        + urlencode(
            {
                "openid.ns": NS,
                "openid.mode": "checkid_setup",
                "openid.claimed_id": IDENTIFIER_SELECT,
                "openid.identity": IDENTIFIER_SELECT,
                "openid.return_to": return_url(config, state),
                "openid.realm": config.browser_origin + "/",
            }
        )
    )


async def bounded_body(
    client: httpx.AsyncClient, method: str, url: str, data: dict[str, str] | None = None
) -> str:
    async with client.stream(method, url, data=data) as response:
        if response.status_code != 200:
            raise OpenIDRejected()
        body = bytearray()
        async for chunk in response.aiter_bytes():
            body.extend(chunk)
            if len(body) > 65536:
                raise OpenIDRejected()
        return body.decode("utf-8", errors="strict")


def discovered_identity(body: str, claimed_id: str) -> None:
    if "<!DOCTYPE" in body.upper() or "<!ENTITY" in body.upper():
        raise OpenIDRejected()
    try:
        root = ElementTree.fromstring(body)
    except ElementTree.ParseError:
        raise OpenIDRejected() from None
    xrd = "{xri://$xrd*($v*2.0)}"
    for service in root.iter(xrd + "Service"):
        types = [node.text for node in service.findall(xrd + "Type")]
        endpoints = [node.text for node in service.findall(xrd + "URI")]
        local_ids = [node.text for node in service.findall(xrd + "LocalID")]
        if NS + "/signon" in types and PROVIDER in endpoints:
            if not local_ids or local_ids == [claimed_id]:
                return
    raise OpenIDRejected()


def positive_response(body: str) -> bool:
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if not line or ":" not in line:
            return False
        key, value = line.split(":", 1)
        if key in fields or key not in {"ns", "is_valid", "invalidate_handle"}:
            return False
        fields[key] = value
    return fields.get("ns") == NS and fields.get("is_valid") == "true"


async def verify_assertion(
    params: dict[str, str], config: Settings, client: httpx.AsyncClient
) -> tuple[str, str]:
    try:
        if params.get("openid.ns") != NS or params.get("openid.mode") != "id_res":
            raise OpenIDRejected()
        if params.get("openid.op_endpoint") != PROVIDER:
            raise OpenIDRejected()
        if params.get("openid.return_to") != return_url(config, params["state"]):
            raise OpenIDRejected()
        claimed = params.get("openid.claimed_id", "")
        match = CLAIM.fullmatch(claimed)
        if not match or params.get("openid.identity") != claimed:
            raise OpenIDRejected()
        # Steam public individual accounts: universe 1, individual type, instance 1.
        steam_id = match.group(1)
        if not 76561197960265728 <= int(steam_id) <= 76561202255233023:
            raise OpenIDRejected()
        signed = params.get("openid.signed", "").split(",")
        if len(signed) != len(set(signed)) or not SIGNED.issubset(signed):
            raise OpenIDRejected()
        if any(not params.get("openid." + key) for key in signed):
            raise OpenIDRejected()
        signature = base64.b64decode(params.get("openid.sig", ""), validate=True)
        if not 20 <= len(signature) <= 128:
            raise OpenIDRejected()
        nonce = params.get("openid.response_nonce", "")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z[^\s]{1,200}", nonce):
            raise OpenIDRejected()
        from datetime import datetime

        timestamp = datetime.fromisoformat(nonce[:20].replace("Z", "+00:00"))
        if not utcnow() - timedelta(seconds=300) <= timestamp <= utcnow() + timedelta(seconds=60):
            raise OpenIDRejected()
        async with asyncio.timeout(config.provider_timeout_seconds):
            # Transport upgrade only: retain the exact asserted HTTP/HTTPS identifier.
            discovery = await bounded_body(
                client, "GET", "https://steamcommunity.com/openid/id/" + steam_id
            )
            discovered_identity(discovery, claimed)
            data = {key: value for key, value in params.items() if key.startswith("openid.")}
            data["openid.mode"] = "check_authentication"
            response = await bounded_body(client, "POST", PROVIDER, data)
            if not positive_response(response):
                raise OpenIDRejected()
        return steam_id, nonce
    except (KeyError, ValueError, UnicodeError, binascii.Error, httpx.HTTPError, TimeoutError):
        raise OpenIDRejected() from None
