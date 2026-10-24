import logging
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from steamscope_social.core.config import Settings
from steamscope_social.core.logging import configure_logging
from steamscope_social.modules.auth.openid import (
    NS,
    OpenIDRejected,
    authentication_url,
    callback_parameters,
    positive_response,
    verify_assertion,
)
from steamscope_social.modules.auth.security import csrf_token, digest, new_token
from steamscope_social.modules.privacy.policy import can_view
from steamscope_social.modules.users.schemas import ProfileUpdate
from tests.provider_fixtures import SteamTransport, assertion


async def verify(params, settings, provider=None):
    provider = provider or SteamTransport()
    async with httpx.AsyncClient(transport=httpx.MockTransport(provider)) as client:
        return await verify_assertion(params, settings, client)


@pytest.mark.parametrize("scheme", ["http", "https"])
async def test_valid_assertion_performs_discovery_and_direct_verification(settings, scheme):
    params = assertion(authentication_url(settings, new_token()))
    params["openid.claimed_id"] = params["openid.claimed_id"].replace("http:", scheme + ":")
    params["openid.identity"] = params["openid.claimed_id"]
    provider = SteamTransport()
    assert (await verify(params, settings, provider))[0] == "76561198000000001"
    assert len(provider.calls) == 2


@pytest.mark.parametrize(
    "key,value",
    [
        ("openid.ns", "openid-connect"),
        ("openid.mode", "cancel"),
        ("openid.op_endpoint", "https://attacker.invalid/verify"),
        ("openid.return_to", "http://127.0.0.1:3100/evil"),
        ("openid.identity", "http://steamcommunity.com/openid/id/76561198000000002"),
        (
            "openid.claimed_id",
            "https://steamcommunity.com.attacker.invalid/openid/id/76561198000000001",
        ),
        ("openid.signed", "op_endpoint,return_to"),
        ("openid.response_nonce", "2000-01-01T00:00:00Zold"),
        ("openid.response_nonce", "2099-01-01T00:00:00Zfuture"),
        ("openid.response_nonce", "invalid"),
        ("openid.sig", "bad signature"),
        ("openid.assoc_handle", ""),
    ],
)
async def test_bad_assertions_never_contact_callback_selected_hosts(settings, key, value):
    params = assertion(authentication_url(settings, new_token()), **{key: value})
    provider = SteamTransport()
    with pytest.raises(OpenIDRejected):
        await verify(params, settings, provider)
    assert not provider.calls


@pytest.mark.parametrize(
    "body",
    [
        "is_valid:true\n",
        f"ns:{NS}\nis_valid:false\n",
        f"ns:{NS}\nis_valid:true\nis_valid:false\n",
        f"ns:{NS}\nis_valid:true-ish\n",
        "<html>error</html>",
    ],
)
def test_strict_provider_response(body):
    assert not positive_response(body)


async def test_discovery_and_provider_fail_closed(settings):
    params = assertion(authentication_url(settings, new_token()))
    for mode in ["timeout", "bad-discovery", "malformed", "entity", "wrong-local-id"]:
        provider = SteamTransport()
        if mode == "timeout":
            provider.failure = "timeout"
        if mode == "bad-discovery":
            provider.discovery = provider.discovery.replace("/openid/login", "/evil")
        if mode == "malformed":
            provider.verification = "is_valid:true"
        if mode == "entity":
            provider.discovery = "<!DOCTYPE x>" + provider.discovery
        if mode == "wrong-local-id":
            provider.discovery = provider.discovery.replace(
                "</Service>", "<LocalID>someone-else</LocalID></Service>"
            )
        with pytest.raises(OpenIDRejected):
            await verify(params, settings, provider)


def test_duplicate_or_conflicting_parameters_rejected():
    state = new_token()
    for pairs in [
        [("state", state), ("state", state)],
        [("state", state), ("openid.mode", "cancel"), ("openid.mode", "id_res")],
        [("state", state), ("destination", "https://evil.invalid")],
    ]:
        with pytest.raises(OpenIDRejected):
            callback_parameters(pairs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"browser_origin": "http://localhost:3100"},
        {"browser_origin": "http://public.example"},
        {
            "environment": "production",
            "database_url": "postgresql+asyncpg://u:p@localhost/steamscope_social_prod",
        },
        {"cookie_secure": True},
        {"browser_origin": "http://127.0.0.1:3100/"},
    ],
)
def test_unsafe_cookie_config_rejected(kwargs):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **kwargs)


def test_secure_production_configuration_and_token_properties():
    config = Settings(
        _env_file=None,
        environment="production",
        cookie_secure=True,
        browser_origin="https://example.test",
        database_url="postgresql+asyncpg://u:p@db/steamscope_social_prod",
    )
    assert config.callback_url == "https://example.test/api/v1/auth/steam/callback"
    first, second = new_token(), new_token()
    assert len(first) == 43 and first != second and digest(first) != first
    assert csrf_token(first) != csrf_token(second)


@pytest.mark.parametrize(
    "body",
    [
        {"id": str(uuid4())},
        {"steam_id": "76561198000000001"},
        {"status": "active"},
        {"handle": "bad space"},
        {"locale": "invalid"},
        {"timezone": "../etc/passwd"},
        {"display_name": None},
    ],
)
def test_profile_validation_and_mass_assignment(body):
    with pytest.raises(ValidationError):
        ProfileUpdate(**body)


def test_policy_has_no_fake_friends():
    owner, other = uuid4(), uuid4()
    assert can_view(owner, owner, "private", account_active=True, source_available=True)
    assert not can_view(owner, other, "connections", account_active=True, source_available=True)
    assert not can_view(owner, owner, "public", account_active=False, source_available=True)


def test_network_and_access_loggers_disabled():
    configure_logging()
    assert all(logging.getLogger(name).disabled for name in ["httpx", "httpcore", "uvicorn.access"])
