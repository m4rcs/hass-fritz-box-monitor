"""Tests for the FRITZ!Box Monitor config flow.

The flow talks to the faked FRITZ!Box (see conftest.py); these tests
pin the schema, the error mapping, the MAC unique id, the reconfigure
flow and the options flow.
"""

from collections.abc import Callable
import json
from typing import Any
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)
from yarl import URL

from custom_components.fritz_box_monitor.const import (
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)

from .const import (
    FAKE_BASE_URL,
    FAKE_HOST,
    FAKE_MAC,
    FAKE_PASSWORD,
    FAKE_USERNAME,
)


def _user_input() -> dict[str, str]:
    """Return the data a user submits in the flow."""
    return {
        CONF_HOST: FAKE_HOST,
        CONF_USERNAME: FAKE_USERNAME,
        CONF_PASSWORD: FAKE_PASSWORD,
    }


async def _start_flow(hass: HomeAssistant) -> Any:
    """Start the config flow."""
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _submit(hass: HomeAssistant, user_input: dict[str, str]) -> Any:
    """Start the flow and submit the given user data."""
    result = await _start_flow(hass)
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )


async def test_form_shown(hass: HomeAssistant) -> None:
    """The user step asks for host, username and password."""
    result = await _start_flow(hass)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_setup_creates_entry(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """A successful flow stores the credentials and the serial number."""
    result = await _start_flow(hass)

    with patch(
        "custom_components.fritz_box_monitor.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _user_input()
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "FRITZ!Box 6660 Cable"
    assert result["data"] == _user_input()

    entry = hass.config_entries.async_entries()[0]
    assert entry.unique_id == FAKE_MAC


async def test_duplicate_serial_aborts(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """A modem that is already set up aborts the flow."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=FAKE_MAC)
    entry.add_to_hass(hass)

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_connection_error_shows_cannot_connect(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Connection problems during the flow map to cannot_connect."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2", exc=TimeoutError()
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_auth_failure_shows_invalid_auth(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A rejected login maps to invalid_auth."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_denied.xml"),
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_blocked_shows_login_blocked_with_time(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A blocked login maps to login_blocked with the remaining time."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge_blocked.xml"),
    )

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "login_blocked"}
    assert result["description_placeholders"] == {"block_time": "60"}


async def test_unexpected_error_shows_unknown(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """Errors outside the client contract map to unknown."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    aioclient_mock.post(f"{FAKE_BASE_URL}/data.lua", text="<not json>")

    result = await _submit(hass, _user_input())

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_reconfigure_form_prefilled(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """The reconfigure form prefills host and username, not the password."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=FAKE_MAC, data=_user_input()
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    schema = result["data_schema"]
    assert schema is not None
    defaults = {}
    for key in schema.schema:
        factory = getattr(key, "default", None)
        if callable(factory):
            defaults[str(key)] = factory()
    assert defaults[CONF_HOST] == FAKE_HOST
    assert defaults[CONF_USERNAME] == FAKE_USERNAME


async def test_reconfigure_updates_entry_and_reloads(
    hass: HomeAssistant, mock_fritz_box: None
) -> None:
    """A successful reconfigure stores the new password and reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=FAKE_MAC, data=_user_input()
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )

    new_input = {**_user_input(), CONF_PASSWORD: "new-password"}
    with patch(
        "custom_components.fritz_box_monitor.async_setup_entry",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], new_input
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"
    assert entry.unique_id == FAKE_MAC


async def test_reconfigure_wrong_password_keeps_data(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A rejected login shows the error and leaves the entry untouched."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=FAKE_MAC, data=_user_input()
    )
    entry.add_to_hass(hass)

    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_denied.xml"),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {**_user_input(), CONF_PASSWORD: "wrong-password"},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_PASSWORD] == FAKE_PASSWORD


async def test_reconfigure_foreign_mac_aborts(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A different modem answering aborts instead of re-pointing."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=FAKE_MAC, data=_user_input()
    )
    entry.add_to_hass(hass)

    doc_ov = json.loads(load_fritz_fixture("doc_ov.json"))
    info_details = doc_ov["data"]["connectionData"]["infoLeft"]["details"]
    for detail in info_details:
        detail["value"] = "11:22:33:44:55:66"
    doc_info = json.loads(load_fritz_fixture("doc_info.json"))

    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    pages = {
        "docOv": json.dumps(doc_ov),
        "docInfo": json.dumps(doc_info),
    }

    async def _serve(method: str, url: Any, data: Any) -> Any:
        """Serve the page matching the request."""
        page = str(dict(data or {}).get("page"))
        return AiohttpClientMockResponse(method, URL(url), text=pages[page])

    aioclient_mock.post(f"{FAKE_BASE_URL}/data.lua", side_effect=_serve)
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/api/v0/generic/uimodlogic",
        text=load_fritz_fixture("uimodlogic.json"),
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _user_input()
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"


async def test_options_flow_shows_current_interval(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> None:
    """The options form defaults to the current poll interval."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_updates_interval_and_reloads(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> None:
    """A new interval is stored and the reloaded coordinator uses it."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 60}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options[CONF_UPDATE_INTERVAL] == 60
    coordinator = mock_config_entry.runtime_data
    assert coordinator.update_interval.total_seconds() == 60


async def test_options_flow_rejects_intervals_below_minimum(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_fritz_box: None,
) -> None:
    """Intervals below the minimum show an error and store nothing."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(
        mock_config_entry.entry_id
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 5}
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "interval_too_low"}
    assert CONF_UPDATE_INTERVAL not in mock_config_entry.options


def _register_success_flow(
    aioclient_mock: Any, load_fritz_fixture: Callable[[str], str]
) -> None:
    """Register the routes of a healthy FRITZ!Box (MAC FAKE_MAC)."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_success.xml"),
    )
    pages = {
        "docOv": load_fritz_fixture("doc_ov.json"),
        "docInfo": load_fritz_fixture("doc_info.json"),
    }

    async def _serve(method: str, url: Any, data: Any) -> Any:
        """Serve the page matching the request."""
        page = str(dict(data or {}).get("page"))
        return AiohttpClientMockResponse(method, URL(url), text=pages[page])

    aioclient_mock.post(f"{FAKE_BASE_URL}/data.lua", side_effect=_serve)
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/api/v0/generic/uimodlogic",
        text=load_fritz_fixture("uimodlogic.json"),
    )


def _register_denied_login(
    aioclient_mock: Any, load_fritz_fixture: Callable[[str], str]
) -> None:
    """Register a challenge plus a rejected login."""
    aioclient_mock.get(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_challenge.xml"),
    )
    aioclient_mock.post(
        f"{FAKE_BASE_URL}/login_sid.lua?version=2",
        text=load_fritz_fixture("login_denied.xml"),
    )


async def test_setup_auth_failure_starts_reauth(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """A wrong password at setup marks the entry and starts a reauth."""
    mock_config_entry.add_to_hass(hass)
    _register_denied_login(aioclient_mock, load_fritz_fixture)

    assert not await hass.config_entries.async_setup(
        mock_config_entry.entry_id
    )
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": mock_config_entry.entry_id,
        },
        data=mock_config_entry.data,
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"


async def test_reauth_flow_wrong_then_correct_password(
    hass: HomeAssistant,
    aioclient_mock: Any,
    load_fritz_fixture: Callable[[str], str],
) -> None:
    """Reauth: wrong password shows an error, the right one reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=FAKE_MAC, data=_user_input()
    )
    entry.add_to_hass(hass)
    _register_denied_login(aioclient_mock, load_fritz_fixture)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_REAUTH,
            "entry_id": entry.entry_id,
        },
        data=entry.data,
    )

    # Still the wrong password: the form shows invalid_auth.
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "still-wrong"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.state is ConfigEntryState.SETUP_ERROR

    # The password is fixed on the box: the same reauth flow reloads.
    aioclient_mock.clear_requests()
    _register_success_flow(aioclient_mock, load_fritz_fixture)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "fixed-password"}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.state is ConfigEntryState.LOADED
    assert entry.data[CONF_PASSWORD] == "fixed-password"
