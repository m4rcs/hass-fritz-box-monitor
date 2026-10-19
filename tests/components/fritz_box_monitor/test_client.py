"""Tests for the FRITZ!Box Monitor client.

The client is exercised against a faked FRITZ!Box web UI: aioclient_mock
replaces the shared aiohttp session and serves the canned responses from
the fixtures directory (real captured payloads, sanitized). These tests
pin the implementation of client.py.
"""

from collections.abc import Callable
from typing import Any

from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from yarl import URL

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
    FAKE_MAC,
    FAKE_PASSWORD,
    FAKE_SID,
    FAKE_USERNAME,
)


def _ds_channel(
    channel_id: int,
    frequency: float,
    power: str,
    snr: float,
    correctable: int,
    uncorrectable: int,
) -> DocsisChannel:
    """Build an expected DOCSIS 3.0 downstream channel."""
    return DocsisChannel(
        channel_id=channel_id,
        docsis_version="3.0",
        frequency=frequency,
        power=float(power),
        modulation="256QAM",
        snr=snr,
        correctable_errors=correctable,
        uncorrectable_errors=uncorrectable,
    )


def _ds31_channel(
    channel_id: int,
    frequency: float,
    power: str,
    snr: float,
    uncorrectable: int,
) -> DocsisChannel:
    """Build an expected DOCSIS 3.1 downstream channel."""
    return DocsisChannel(
        channel_id=channel_id,
        docsis_version="3.1",
        frequency=frequency,
        power=float(power),
        modulation="4096QAM",
        snr=snr,
        correctable_errors=None,
        uncorrectable_errors=uncorrectable,
    )


def _us_channel(
    channel_id: int,
    frequency: float,
    power: str,
    modulation: str = "64QAM",
    docsis_version: str = "3.0",
) -> DocsisChannel:
    """Build an expected upstream channel."""
    return DocsisChannel(
        channel_id=channel_id,
        docsis_version=docsis_version,
        frequency=frequency,
        power=float(power),
        modulation=modulation,
    )


EXPECTED_STATUS = CableModemStatus(
    mac=FAKE_MAC,
    model="FRITZ!Box 6660 Cable",
    connection_status="ready",
    os_version="8.25",
    ds_rate=1126.4,
    us_rate=52.5,
    downstream=(
        # DOCSIS 3.0, in reported order.
        _ds_channel(8, 618.0, "16.0", 39.0, 986, 0),
        _ds_channel(3, 570.0, "16.6", 39.0, 616, 0),
        _ds_channel(4, 578.0, "16.6", 38.6, 669, 0),
        _ds_channel(5, 586.0, "16.5", 40.4, 854, 0),
        _ds_channel(6, 594.0, "16.4", 40.4, 871, 0),
        _ds_channel(7, 602.0, "16.3", 39.0, 929, 0),
        _ds_channel(9, 626.0, "16.0", 38.6, 900, 0),
        _ds_channel(10, 634.0, "16.3", 40.4, 909, 0),
        _ds_channel(11, 642.0, "16.5", 39.0, 936, 0),
        _ds_channel(12, 650.0, "16.5", 39.0, 982, 0),
        _ds_channel(13, 658.0, "16.3", 39.0, 1162, 0),
        _ds_channel(14, 666.0, "16.6", 39.0, 1145, 0),
        _ds_channel(15, 674.0, "16.5", 39.0, 1074, 0),
        _ds_channel(16, 682.0, "16.7", 40.9, 1030, 0),
        _ds_channel(17, 690.0, "16.8", 39.0, 969, 0),
        _ds_channel(1, 114.0, "18.4", 40.4, 0, 0),
        _ds_channel(2, 130.0, "17.6", 40.9, 1, 0),
        _ds_channel(18, 698.0, "17.0", 39.0, 892, 0),
        _ds_channel(19, 706.0, "17.4", 39.0, 731, 0),
        _ds_channel(20, 714.0, "17.8", 40.4, 660, 0),
        _ds_channel(21, 722.0, "18.2", 40.4, 1674, 1120),
        _ds_channel(22, 730.0, "18.4", 40.4, 6518, 1985),
        _ds_channel(23, 738.0, "18.6", 40.4, 466, 0),
        _ds_channel(24, 746.0, "18.4", 40.4, 421, 0),
        # DOCSIS 3.1: negative mse becomes a positive SNR, 3.1 reports
        # MER directly, frequencies are band midpoints in MHz.
        _ds31_channel(193, 229.975, "17.1", 43.0, 130),
        _ds31_channel(194, 805.975, "14.2", 39.0, 178),
    ),
    upstream=(
        _us_channel(1, 30.8, "28.8"),
        _us_channel(4, 51.0, "29.5"),
        _us_channel(3, 44.6, "29.0"),
        _us_channel(2, 37.2, "29.0"),
        _us_channel(41, 47.275, "24.0", "128QAM", "3.1"),
    ),
)


def _doc_page_dispatch(
    load_fritz_fixture: Callable[[str], str],
) -> Callable[[str, Any, Any], Any]:
    """Return a side_effect serving both data.lua pages like the box."""

    pages = {
        "docOv": load_fritz_fixture("doc_ov.json"),
        "docInfo": load_fritz_fixture("doc_info.json"),
    }

    async def _serve(method: str, url: URL, data: Any) -> Any:
        """Serve the canned response matching the requested page."""
        page = str(dict(data or {}).get("page"))
        return AiohttpClientMockResponse(method, URL(url), text=pages[page])

    return _serve


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


async def test_get_status_parses_both_pages(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """get_status combines docOv identity and docInfo channels."""
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


async def test_doc_pages_requested_like_the_web_ui(
    hass: HomeAssistant, aioclient_mock: Any, mock_fritz_box: None
) -> None:
    """Both data.lua pages are fetched with the web UI request shape."""
    await _client(hass).get_status()

    data_posts = _calls_to(aioclient_mock, "data.lua")
    assert len(data_posts) == 2

    pages = [dict(call[2])["page"] for call in data_posts]
    assert pages == ["docOv", "docInfo"]

    for call in data_posts:
        assert dict(call[2]) == {
            "xhr": "1",
            "sid": FAKE_SID,
            "lang": "en",
            "page": dict(call[2])["page"],
            "xhrId": "all",
        }


async def test_os_version_requested_with_avm_sid_header(
    hass: HomeAssistant, aioclient_mock: Any, mock_fritz_box: None
) -> None:
    """The FRITZ!OS version endpoint authenticates via an AVM-SID header."""
    await _client(hass).get_status()

    version_gets = _calls_to(aioclient_mock, "uimodlogic", "GET")
    assert len(version_gets) == 1
    assert str(version_gets[0][1]).endswith("/api/v0/generic/uimodlogic")
    headers = version_gets[0][3]
    assert headers is not None
    assert headers["Authorization"] == f"AVM-SID {FAKE_SID}"


async def test_missing_os_version_api_is_tolerated(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A box without the version API still reports everything else."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/data.lua",
        side_effect=_doc_page_dispatch(load_fritz_fixture),
    )
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/api/v0/generic/uimodlogic", status=404
    )

    status = await _client(hass).get_status()

    assert status.os_version is None
    assert status.model == "FRITZ!Box 6660 Cable"
    assert status.downstream[0].channel_id == 8


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


@pytest.mark.parametrize("exc", [TimeoutError(), ClientError()])
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
    """A failing data page after a successful login maps to an error."""
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
    """When the docOv fetch is rejected, the client re-logins once."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    # The SID is expired, so every data page fetch is rejected. The
    # client must re-login (a second login POST) and retry once before
    # giving up.
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/data.lua", text="forbidden", status=403
    )

    with pytest.raises(FritzBoxMonitorConnectionError):
        await _client(hass).get_status()

    assert len(_calls_to(aioclient_mock, "login_sid.lua", "POST")) == 2
    assert len(_calls_to(aioclient_mock, "data.lua")) == 2
