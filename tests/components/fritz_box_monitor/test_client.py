"""Tests for the FRITZ!Box Monitor client.

The client is exercised against a faked FRITZ!Box web UI: aioclient_mock
replaces the shared aiohttp session and serves the canned responses from
the fixtures directory. These tests drive the implementation of
client.py (TDD); they are expected to fail until it is implemented.
"""


from collections.abc import Callable
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.fritz_box_monitor.client import (
    CableModemStatus,
    DocsisChannel,
    FritzBoxMonitorAuthError,
    FritzBoxMonitorClient,
    FritzBoxMonitorConnectionError,
    FritzBoxMonitorLoginBlockedError,
)

from .const import (
    FAKE_BASE_URL,
    FAKE_BLOCK_TIME,
    FAKE_HOST,
    FAKE_LOGIN_RESPONSE,
    FAKE_PASSWORD,
    FAKE_SID,
    FAKE_USERNAME,
)

EXPECTED_STATUS = CableModemStatus(
    serial_number="123456789012",
    model="FRITZ!Box 6591 Cable",
    firmware="7.29",
    connection_status="online",
    downstream=(
        DocsisChannel(
            channel_id=1,
            docsis_version="3.0",
            frequency=306_000_000,
            power=3.5,
            modulation="256QAM",
            snr=39.8,
            correctable_errors=12,
            uncorrectable_errors=0,
        ),
        DocsisChannel(
            channel_id=5,
            docsis_version="3.0",
            frequency=330_000_000,
            power=4.1,
            modulation="256QAM",
            snr=40.2,
            correctable_errors=340,
            uncorrectable_errors=7,
        ),
        DocsisChannel(
            channel_id=33,
            docsis_version="3.1",
            frequency=858_000_000,
            power=6.5,
            modulation="4096QAM",
            snr=43.1,
            correctable_errors=0,
            uncorrectable_errors=0,
        ),
    ),
    upstream=(
        DocsisChannel(
            channel_id=4,
            docsis_version="3.0",
            frequency=21_000_000,
            power=110.5,
            modulation="64QAM",
        ),
        DocsisChannel(
            channel_id=6,
            docsis_version="3.0",
            frequency=39_000_000,
            power=111.0,
            modulation="64QAM",
        ),
        DocsisChannel(
            channel_id=10,
            docsis_version="3.1",
            frequency=57_000_000,
            power=112.5,
            modulation="4096QAM",
        ),
    ),
)


def _client(hass: HomeAssistant) -> FritzBoxMonitorClient:
    """Return a client talking to the faked FRITZ!Box."""
    return FritzBoxMonitorClient(
        FAKE_HOST,
        session=async_get_clientsession(hass),
        username=FAKE_USERNAME,
        password=FAKE_PASSWORD,
    )


def _calls_to(
    aioclient_mock: Any, fragment: str, method: str | None = None
) -> list[tuple]:
    """Return recorded mock calls (method, url, data, headers) by URL."""
    return [
        call
        for call in aioclient_mock.mock_calls
        if fragment in str(call[1])
        and (method is None or call[0].upper() == method)
    ]


async def test_get_status_parses_doc_info(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """get_status logs in and parses the docInfo page into a status."""
    status = await _client(hass).get_status()

    assert status == EXPECTED_STATUS


async def test_login_sends_pbkdf2_response(
    hass: HomeAssistant, aioclient_mock: Any, mock_fritz_box: None
) -> None:
    """The client answers the v2 challenge with the PBKDF2 response."""
    await _client(hass).get_status()

    login_posts = _calls_to(aioclient_mock, "login_sid.lua", "POST")
    assert len(login_posts) == 1

    data = dict(login_posts[0][2])
    assert data["username"] == FAKE_USERNAME
    assert data["response"] == FAKE_LOGIN_RESPONSE


async def test_challenge_is_requested_with_version_2(
    hass: HomeAssistant, aioclient_mock: Any, mock_fritz_box: None
) -> None:
    """The client requests the PBKDF2-capable v2 login endpoint."""
    await _client(hass).get_status()

    challenge_gets = [
        call
        for call in aioclient_mock.mock_calls
        if call[0].upper() == "GET" and "login_sid.lua" in str(call[1])
    ]
    assert len(challenge_gets) == 1
    assert str(challenge_gets[0][1]).endswith("login_sid.lua?version=2")


async def test_data_page_requested_with_sid(
    hass: HomeAssistant, aioclient_mock: Any, mock_fritz_box: None
) -> None:
    """The docInfo page is fetched by POST with the session id."""
    await _client(hass).get_status()

    data_posts = _calls_to(aioclient_mock, "data.lua")
    assert len(data_posts) == 1

    data = dict(data_posts[0][2])
    assert data["sid"] == FAKE_SID
    assert data["page"] == "docInfo"


async def test_wrong_credentials_raises_auth_error(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A login that leaves the SID zeroed maps to an auth error."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_denied.xml"),
    )

    with pytest.raises(FritzBoxMonitorAuthError):
        await _client(hass).get_status()


@pytest.mark.parametrize(
    "exc", [TimeoutError(), ClientError()]
)
async def test_unreachable_modem_raises_connection_error(
    hass: HomeAssistant, aioclient_mock: Any, exc: Exception
) -> None:
    """Request failures while reaching the modem map to a connection error."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2", exc=exc
    )

    with pytest.raises(FritzBoxMonitorConnectionError):
        await _client(hass).get_status()


@pytest.mark.parametrize("status", [403, 500])
async def test_data_page_error_raises_connection_error(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
    status: int,
) -> None:
    """A failing docInfo fetch after a successful login maps to an error."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/data.lua", text="forbidden", status=status
    )

    with pytest.raises(FritzBoxMonitorConnectionError):
        await _client(hass).get_status()


async def test_blocked_challenge_raises_login_blocked(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A block during the challenge aborts before any login attempt."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge_blocked.xml"),
    )

    with pytest.raises(FritzBoxMonitorLoginBlockedError) as exc_info:
        await _client(hass).get_status()

    assert exc_info.value.block_time == FAKE_BLOCK_TIME
    assert isinstance(exc_info.value, FritzBoxMonitorAuthError)
    assert _calls_to(aioclient_mock, "login_sid.lua", "POST") == []


async def test_blocked_login_raises_login_blocked(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A block reported by the login POST maps to the blocked error."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_blocked.xml"),
    )

    with pytest.raises(FritzBoxMonitorLoginBlockedError) as exc_info:
        await _client(hass).get_status()

    assert exc_info.value.block_time == FAKE_BLOCK_TIME
    assert isinstance(exc_info.value, FritzBoxMonitorAuthError)


async def test_expired_sid_triggers_relogin(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """When the docInfo fetch is rejected, the client re-logins once."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    # The SID is expired, so every docInfo fetch is rejected. The client
    # must re-login (a second login POST) and retry once before giving up.
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/data.lua", text="forbidden", status=403
    )

    with pytest.raises(FritzBoxMonitorConnectionError):
        await _client(hass).get_status()

    assert len(_calls_to(aioclient_mock, "login_sid.lua", "POST")) == 2
    assert len(_calls_to(aioclient_mock, "data.lua")) == 2
